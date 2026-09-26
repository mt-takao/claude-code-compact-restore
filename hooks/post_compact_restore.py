#!/usr/bin/env python3
"""
SessionStart hook: 作業状態をコンテキストへ注入する。

  source=compact           … 圧縮前スナップショット + 作業ノート
  source=startup/resume/clear … 作業ノートのみ

作業ノート・スナップショットはどちらも「そのプロジェクトの」
.claude/context/ から読むので、プロジェクト単位でもユーザー単位でも同じスクリプトで動く。
"""
import json
import os
import sys
from pathlib import Path

SNAPSHOT_MAX = 12000
NOTES_MAX = 6000


def read(p, limit):
    if not p.exists():
        return ""
    body = p.read_text(encoding="utf-8").strip()
    if len(body) > limit:
        body = body[:limit] + f"\n…(以下省略。全文は {p})"
    return body


def main():
    try:
        hook = json.load(sys.stdin)
    except Exception:
        hook = {}
    source = hook.get("source", "")
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR") or hook.get("cwd") or os.getcwd())
    ctx = project_dir / ".claude" / "context"

    parts = []
    if source == "compact":
        snap = read(ctx / "latest-snapshot.md", SNAPSHOT_MAX)
        if snap:
            parts.append(
                "【コンテキスト復元】直前に会話が圧縮されました。以下は圧縮直前の作業状態を"
                "機械的に退避したものです。圧縮サマリーと食い違う場合はこちらの具体的な記録"
                "（タスクリスト・編集ファイル・ユーザー指示）を優先し、下の作業ノートの方針と"
                "合わせて作業を再開してください。不明点は推測せずユーザーに確認してください。\n\n" + snap
            )
    notes = read(ctx / "working-notes.md", NOTES_MAX)
    if notes:
        parts.append(
            "【作業ノート】このプロジェクトで自分（このユーザー）が進めている作業の要点です。"
            "`/checkpoint` で更新されます。\n\n" + notes
        )
    if not parts:
        return 0
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": "\n\n---\n\n".join(parts),
    }}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"[post_compact_restore] {e}", file=sys.stderr)
        sys.exit(0)
