#!/usr/bin/env python3
"""
PreCompact hook: 圧縮（/compact・auto-compact）の直前に作業状態をファイルへ退避する。

退避先:
  .claude/context/snapshots/<timestamp>.md   … 履歴（直近 KEEP 件を保持）
  .claude/context/latest-snapshot.md         … 圧縮後に再注入される最新版

抽出する情報（LLMを使わず transcript から機械的に取れるもの）:
  - 直近のユーザー指示
  - 最新の TodoWrite（タスクリストと進捗）
  - 編集・作成したファイル
  - 直前の Claude の発言（どこまで進んでいたか）
  - git ブランチ / 未コミット変更
"""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

RECENT_USER_PROMPTS = 8      # 残すユーザー指示の数
PROMPT_MAX_CHARS = 600       # 1指示あたりの最大文字数
LAST_ASSISTANT_MAX = 1500    # 直前のClaude発言の最大文字数
KEEP = 20                    # 保持するスナップショット数
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


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
             "Caveat:", "[Request interrupted")
    return not text.startswith(noise)


def clip(s, n):
    s = s.strip()
    return s if len(s) <= n else s[:n] + " …(省略)"


def extract(entries, project_dir):
    prompts, files, todos, last_assistant = [], [], None, ""
    for e in entries:
        if is_real_user_prompt(e):
            prompts.append(text_of(e["message"]["content"]))
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
            if name in EDIT_TOOLS:
                fp = inp.get("file_path") or inp.get("notebook_path")
                if fp:
                    try:
                        fp = str(Path(fp).resolve().relative_to(project_dir))
                    except Exception:
                        pass
                    if fp in files:
                        files.remove(fp)
                    files.append(fp)  # 最後に触ったものが末尾
            elif name == "TodoWrite":
                todos = inp.get("todos")
    return prompts[-RECENT_USER_PROMPTS:], files, todos, last_assistant


def git(args, cwd):
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                           text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def render(hook, prompts, files, todos, last_assistant, project_dir):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    trigger = hook.get("trigger", "unknown")
    focus = (hook.get("custom_instructions") or "").strip()
    L = [f"# 圧縮前スナップショット（{now} / trigger: {trigger}）", ""]
    if focus:
        L += [f"/compact の focus 指定: {focus}", ""]
    sid = os.environ.get("CLAUDE_CODE_REMOTE_SESSION_ID", "")
    if sid:  # クラウドセッション（Projects のスレッドを含む）: 元のトランスクリプトへのリンク
        L += [f"元のセッション: https://claude.ai/code/{sid.replace('cse_', 'session_', 1)}", ""]

    L.append("## 進行中のタスクリスト")
    if todos:
        mark = {"completed": "[x]", "in_progress": "[→]", "pending": "[ ]"}
        for t in todos:
            L.append(f"- {mark.get(t.get('status'), '[ ]')} {t.get('content', '')}")
    else:
        L.append("- （TodoWrite の記録なし）")
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
    prompts, files, todos, last_assistant = extract(entries, project_dir)
    md = render(hook, prompts, files, todos, last_assistant, project_dir)

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
