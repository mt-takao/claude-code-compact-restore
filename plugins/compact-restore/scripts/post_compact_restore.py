#!/usr/bin/env python3
"""
SessionStart hook: 作業状態をコンテキストへ注入する。

  source=compact              … 圧縮前スナップショット + 作業ノート
  source=startup/resume/clear … 作業ノートのみ

クラウドセッション（CLAUDE_CODE_REMOTE=true。Claude Code Projects のスレッドを含む）では、
.claude/context/ がその VM 限りで消えうるため、永続化の案内も添える。
"""
import json
import os
import sys
from pathlib import Path

SNAPSHOT_MAX = 12000
NOTES_MAX = 6000
PROJECT_FILES = Path(os.environ.get("COMPACT_RESTORE_PROJECT_FILES", "/mnt/project-files"))

CLOUD_GUIDE = (
    "【クラウドセッションでの記録先】このセッションはクラウド VM で動いています。"
    "`.claude/context/`（作業ノート・スナップショット）はこの VM 内だけのもので、"
    "他のスレッドや、作り直された VM には引き継がれません。\n"
    "- 作業の途中経過はこまめに commit して push する（コミットされていない変更は VM の再作成で失われうる）\n"
)
PROJECT_GUIDE = (
    "- これは Claude Code Projects のスレッドです。スレッドをまたいで残すべき決定事項・却下した案・"
    "落とし穴は、作業ノートではなく **プロジェクトメモリ** に記憶する（後続のスレッドとコーディネーターが読む）\n"
    "- このスレッド内の進捗（現在地・次にやること）は作業ノートに書く。完了報告には要点を含め、"
    "コーディネーターが報告だけで状況を把握できるようにする\n"
)


def read(p, limit):
    if not p.exists():
        return ""
    body = p.read_text(encoding="utf-8").strip()
    if len(body) > limit:
        body = body[:limit] + f"\n…(以下省略。全文は {p})"
    return body


def environment():
    """local / cloud / project-thread を判定する"""
    if os.environ.get("CLAUDE_CODE_REMOTE") != "true":
        return "local"
    return "project-thread" if PROJECT_FILES.is_dir() else "cloud"


def main():
    try:
        hook = json.load(sys.stdin)
    except Exception:
        hook = {}
    source = hook.get("source", "")
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR") or hook.get("cwd") or os.getcwd())
    ctx = project_dir / ".claude" / "context"
    env = environment()

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
            "`checkpoint` コマンドで更新されます。\n\n" + notes
        )
    if env != "local":
        parts.append(CLOUD_GUIDE + (PROJECT_GUIDE if env == "project-thread" else ""))

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
