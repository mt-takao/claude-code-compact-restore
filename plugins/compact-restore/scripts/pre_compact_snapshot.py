#!/usr/bin/env python3
"""
PreCompact hook: 圧縮（/compact・auto-compact）の直前に作業状態をファイルへ退避する。

退避先:
  .claude/context/snapshots/<timestamp>.md   … 履歴（直近 KEEP 件を保持）
  .claude/context/latest-snapshot.md         … 圧縮後に再注入される最新版

抽出する情報（LLMを使わず transcript から機械的に取れるもの）:
  - 直近のユーザー指示
  - タスクリストと進捗（最新の TodoWrite、または TaskCreate / TaskUpdate の積み重ね）
  - Claude Code Projects のスレッドの進捗表示（最新の update_status）
  - 編集・作成したファイル（一時フォルダの作業ファイルは除き、メモリは別に記録）
  - 直前の Claude の発言（どこまで進んでいたか）
  - git ブランチ / 未コミット変更
"""
import html
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

RECENT_USER_PROMPTS = 8      # 残すユーザー指示の数
PROMPT_MAX_CHARS = 600       # 1指示あたりの最大文字数
LAST_ASSISTANT_MAX = 1500    # 直前のClaude発言の最大文字数
PROGRESS_MAX = 1500          # スレッドの進捗表示の最大文字数
KEEP = 20                    # 保持するスナップショット数
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
# Claude Code Projects のスレッドでは、人間の発言が <wake> の通知データに包まれて届く
WAKE_MESSAGE = re.compile(r'<message\b[^>]*\btrigger="true"[^>]*>(.*?)</message>', re.S)
WAKE_AUTHOR = re.compile(r'\bauthor="([^"]*)"')
TASK_CREATED = re.compile(r"Task #(\S+) created")
# プロジェクト外の編集のうち、使い捨ての作業ファイルとみなす置き場所
TEMP_ROOTS = tuple(dict.fromkeys(
    str(Path(d).resolve()) for d in (tempfile.gettempdir(), "/tmp", "/var/tmp", "/var/folders")))


def read_hook_input():
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def load_transcript(path):
    entries = []
    if not path or not Path(path).exists():
        return entries
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


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


def clip(s, n):
    s = s.strip()
    return s if len(s) <= n else s[:n] + " …(省略)"


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
    return prompts[-RECENT_USER_PROMPTS:], files, memories, todos, last_assistant, progress


def git(args, cwd):
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                           text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def render(hook, prompts, files, memories, todos, last_assistant, progress, project_dir):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    trigger = hook.get("trigger", "unknown")
    focus = (hook.get("custom_instructions") or "").strip()
    L = [f"# 圧縮前スナップショット（{now} / trigger: {trigger}）", ""]
    if focus:
        L += [f"/compact の focus 指定: {focus}", ""]
    sid = os.environ.get("CLAUDE_CODE_REMOTE_SESSION_ID", "")
    if sid:  # クラウドセッション（Projects のスレッドを含む）: 元のトランスクリプトへのリンク
        L += [f"元のセッション: https://claude.ai/code/{sid.replace('cse_', 'session_', 1)}", ""]

    if todos:
        L.append("## 進行中のタスクリスト")
        mark = {"completed": "[x]", "in_progress": "[→]", "pending": "[ ]"}
        for t in todos:
            L.append(f"- {mark.get(t.get('status'), '[ ]')} {t.get('content', '')}")
        L.append("")
    elif not progress:  # Projects のスレッドは進捗表示で足りるので、空の欄は出さない
        L += ["## 進行中のタスクリスト", "- （タスクリストの記録なし）", ""]
    if progress:
        L.append("## スレッドの進捗表示（最新。✓ 完了 / ✱ 作業中 / ○ 未着手）")
        L.append(clip(progress, PROGRESS_MAX))
        L.append("")

    L.append("## 直近のユーザー指示（古い→新しい）")
    if prompts:
        for i, p in enumerate(prompts, 1):
            L.append(f"{i}. " + clip(p, PROMPT_MAX_CHARS).replace("\n", "\n   "))
    else:
        L.append("- （なし）")
    L.append("")

    L.append("## このセッションで編集したファイル（最後に触った順で末尾）")
    L += [f"- {f}" for f in files[-30:]] or ["- （なし）"]
    L.append("")
    if memories:
        L.append("## このセッションで更新したメモリ（プロジェクト外。記憶済みの決定事項の手がかり）")
        L += [f"- {m}" for m in memories[-10:]]
        L.append("")

    branch = git(["branch", "--show-current"], project_dir)
    status = git(["status", "--short"], project_dir)
    if branch or status:
        L.append("## Git 状態")
        if branch:
            L.append(f"- ブランチ: `{branch}`")
        if status:
            lines = status.splitlines()
            L.append("- 未コミットの変更:")
            L.append("```")
            L += lines[:40]
            if len(lines) > 40:
                L.append(f"...ほか {len(lines) - 40} 件")
            L.append("```")
        L.append("")

    L.append("## 圧縮直前の Claude の発言（どこまで進んでいたか）")
    L.append(clip(last_assistant, LAST_ASSISTANT_MAX) if last_assistant else "（なし）")
    L.append("")
    return "\n".join(L)


def main():
    hook = read_hook_input()
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR") or hook.get("cwd") or os.getcwd()).resolve()
    ctx_dir = project_dir / ".claude" / "context"
    snap_dir = ctx_dir / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)

    entries = load_transcript(hook.get("transcript_path"))
    prompts, files, memories, todos, last_assistant, progress = extract(entries, project_dir)
    md = render(hook, prompts, files, memories, todos, last_assistant, progress, project_dir)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (snap_dir / f"{stamp}.md").write_text(md, encoding="utf-8")
    (ctx_dir / "latest-snapshot.md").write_text(md, encoding="utf-8")

    for old in sorted(snap_dir.glob("*.md"))[:-KEEP]:
        old.unlink()
    return 0  # 失敗しても圧縮自体は止めない


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"[pre_compact_snapshot] {e}", file=sys.stderr)
        sys.exit(0)
