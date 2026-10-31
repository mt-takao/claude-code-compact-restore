"""
Claude Code の transcript（JSONL）から、圧縮前に退避する内容を取り出す。

  - 直近のユーザー指示
  - タスクリストと進捗（最新の TodoWrite、または TaskCreate / TaskUpdate の積み重ね）
  - Claude Code Projects のスレッドの進捗表示（最新の update_status）
  - 編集・作成したファイル（一時フォルダの作業ファイルは除き、メモリは別に記録）
  - 直前の Claude の発言（どこまで進んでいたか）

transcript の形式は Claude Code の内部仕様なので、取り出せなかったときは warning を返す。
"""
import html
import json
import os
import re
import tempfile
from pathlib import Path

RECENT_USER_PROMPTS = 8      # 残すユーザー指示の数
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
# Claude Code Projects のスレッドでは、人間の発言が <wake> の通知データに包まれて届く
WAKE_MESSAGE = re.compile(r'<message\b[^>]*\btrigger="true"[^>]*>(.*?)</message>', re.S)
WAKE_AUTHOR = re.compile(r'\bauthor="([^"]*)"')
TASK_CREATED = re.compile(r"Task #(\S+) created")
# プロジェクト外の編集のうち、使い捨ての作業ファイルとみなす置き場所
TEMP_ROOTS = tuple(dict.fromkeys(
    str(Path(d).resolve()) for d in (tempfile.gettempdir(), "/tmp", "/var/tmp", "/var/folders")))


def load_transcript(path):
    """transcript を読む。(エントリ一覧, 読めなかった理由 or "") を返す"""
    if not path:
        return [], "transcript のパスが渡されませんでした"
    p = Path(path)
    if p.suffix == ".zst":
        return [], f"記録が圧縮形式のため読めませんでした（{p.name}）"
    if not p.exists():
        return [], f"記録が見つかりませんでした（{path}）"
    entries = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries, ""


def text_of(content):
    """message.content（文字列 or ブロック配列）からテキスト部分だけ取り出す"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def unwrap_wake(text):
    """<wake> の通知から人間の発言だけを取り出す。人間の発言でなければ None"""
    m = WAKE_MESSAGE.search(text)
    if not m or 'from="human"' not in m.group(0):
        return None
    body = html.unescape(m.group(1)).strip()
    author = WAKE_AUTHOR.search(m.group(0)[:m.group(0).find(">")])
    return f"{author.group(1)}: {body}" if author and body else body or None


def prompt_text(entry):
    text = text_of(entry["message"]["content"]).strip()
    return unwrap_wake(text) if text.startswith("<wake") else text


def is_real_user_prompt(entry):
    """tool_result・メタ情報・コマンド出力・過去の圧縮サマリーを除いた、人間の指示だけを拾う"""
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isCompactSummary"):
        return False
    content = entry.get("message", {}).get("content")
    if isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") == "tool_result" for b in content
    ):
        return False
    text = text_of(content).strip()
    if not text:
        return False
    noise = ("<command-name>", "<local-command-stdout>", "<command-message>",
             "Caveat:", "[Request interrupted",
             "<cross-session-message", "<task-notification")  # 他のセッション・ワーカーからの通知
    return not text.startswith(noise)


def classify(fp, project_dir):
    """編集したパスを (種類, 表示名) にする。種類は file / memory / None（記録しない）"""
    try:
        path = Path(fp).resolve()
    except Exception:
        return "file", fp
    try:
        return "file", str(path.relative_to(project_dir))
    except ValueError:
        pass
    if "memory" in path.parts:  # 自動メモリ・プロジェクトメモリ。一時フォルダの下にあっても残す
        return "memory", str(path)
    if "scratchpad" in path.parts or any(
            str(path) == r or str(path).startswith(r + os.sep) for r in TEMP_ROOTS):
        return None, None
    return "file", str(path)  # 別のリポジトリなど、プロジェクト外でも作業対象のファイル


def touch(items, item):
    if item in items:
        items.remove(item)
    items.append(item)  # 最後に触ったものが末尾


def created_task_ids(entry):
    """TaskCreate の結果（tool_result）から {tool_use_id: タスクID} を取り出す"""
    content = entry.get("message", {}).get("content")
    if entry.get("type") != "user" or not isinstance(content, list):
        return {}
    task = (entry.get("toolUseResult") or {}).get("task") if isinstance(entry.get("toolUseResult"), dict) else None
    found = {}
    for b in content:
        if not isinstance(b, dict) or b.get("type") != "tool_result":
            continue
        m = TASK_CREATED.search(text_of(b.get("content")))
        tid = (task or {}).get("id") if isinstance(task, dict) else None
        tid = tid or (m.group(1).rstrip(":") if m else None)
        if tid:
            found[b.get("tool_use_id")] = str(tid)
    return found


def extract(entries, project_dir):
    prompts, files, memories, todos, last_assistant, progress = [], [], [], None, "", ""
    tasks, creating = {}, {}  # TaskCreate / TaskUpdate: {タスクID: 項目}、{tool_use_id: 作成中の項目}
    for e in entries:
        if is_real_user_prompt(e):
            p = prompt_text(e)
            if p:
                prompts.append(p)
        for use_id, tid in created_task_ids(e).items():
            if use_id in creating:
                tasks[tid] = creating.pop(use_id)
                todos = list(tasks.values())
        if e.get("type") != "assistant":
            continue
        content = e.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        t = text_of(content).strip()
        if t:
            last_assistant = t
        for b in content:
            if not isinstance(b, dict) or b.get("type") != "tool_use":
                continue
            name, inp = b.get("name"), b.get("input", {}) or {}
            if str(name).endswith("__reply") and isinstance(inp.get("text"), str):
                last_assistant = inp["text"].strip() or last_assistant  # Projects でユーザーに送った返信
            elif str(name).endswith("__update_status") and isinstance(inp.get("text"), str):
                progress = inp["text"].strip() or progress  # Projects のスレッドの進捗表示（チェックリスト）
            elif name in EDIT_TOOLS:
                fp = inp.get("file_path") or inp.get("notebook_path")
                if fp:
                    kind, shown = classify(fp, project_dir)
                    if kind:
                        touch(memories if kind == "memory" else files, shown)
            elif name == "TodoWrite":
                todos = inp.get("todos")
            elif name == "TaskCreate":
                creating[b.get("id")] = {"content": inp.get("subject") or inp.get("description") or "",
                                         "status": "pending"}
            elif name == "TaskUpdate" and inp.get("taskId") is not None:
                tid = str(inp["taskId"])
                if inp.get("status") == "deleted":
                    tasks.pop(tid, None)
                else:  # 圧縮より前に作られて記録に残っていないタスクも、番号で残す
                    item = tasks.setdefault(tid, {"content": f"タスク #{tid}", "status": "pending"})
                    if inp.get("subject"):
                        item["content"] = inp["subject"]
                    if inp.get("status"):
                        item["status"] = inp["status"]
                todos = list(tasks.values())
    return {"prompts": prompts[-RECENT_USER_PROMPTS:], "files": files, "memories": memories,
            "todos": todos, "last_assistant": last_assistant, "progress": progress}


def read(path, project_dir):
    """transcript から退避する内容を取り出す。読めない・形式が変わったときは warning に理由を入れる"""
    entries, problem = load_transcript(path)
    data = extract(entries, project_dir)
    known = sum(1 for e in entries if isinstance(e, dict) and e.get("type") in ("user", "assistant")
                and isinstance(e.get("message"), dict))
    if problem:
        data["warning"] = problem + "。git の状態だけを記録しています"
    elif entries and not known:
        data["warning"] = ("記録は読めましたが、指示や発言を1件も取り出せませんでした。"
                           "Claude Code の更新で記録の形式が変わった可能性があります")
    return data
