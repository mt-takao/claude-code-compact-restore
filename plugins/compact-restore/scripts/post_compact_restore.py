#!/usr/bin/env python3
"""
SessionStart hook: 作業状態をコンテキストへ注入する。

  source=compact              … 圧縮前スナップショット + 作業ノート
  source=startup/resume/clear … 作業ノートのみ

注入する文章は、フック出力の上限に収まるよう優先度の低いものから削る（compact_restore_core.Injection）。
上限は環境変数 COMPACT_RESTORE_MAX_CHARS で変えられる。

クラウドセッション（CLAUDE_CODE_REMOTE=true。Claude Code Projects のスレッドを含む）では、
.claude/context/ がその VM 限りで消えうるため、永続化の案内も添える。
"""
import json
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # 導入先の hooks フォルダに __pycache__ を作らない
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PROJECT_FILES = Path(os.environ.get("COMPACT_RESTORE_PROJECT_FILES", "/mnt/project-files"))

RESTORE_INTRO = (
    "【コンテキスト復元】直前に会話が圧縮されました。以下は圧縮直前の作業状態を"
    "機械的に退避したものです。圧縮サマリーと食い違う場合はこちらの具体的な記録"
    "（タスクリスト・編集ファイル・ユーザー指示）を優先し、下の作業ノートの方針と"
    "合わせて作業を再開してください。不明点は推測せずユーザーに確認してください。"
)
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


def read(p):
    return p.read_text(encoding="utf-8").strip() if p.exists() else ""


def environment():
    """local / cloud / project-thread を判定する"""
    if os.environ.get("CLAUDE_CODE_REMOTE") != "true":
        return "local"
    return "project-thread" if PROJECT_FILES.is_dir() else "cloud"


def main():
    import compact_restore_core as core

    hook = core.read_hook_input()
    ctx = core.context_dir(core.project_root(hook))
    env = environment()
    inj = core.Injection(core.budget())

    if hook.get("source", "") == "compact":
        snap_path = ctx / core.AGENTS["claude"]["latest"]
        snap = read(snap_path)
        if snap:
            inj.set_snapshot(RESTORE_INTRO, snap, snap_path)
    notes_path = ctx / core.NOTES_NAME
    notes = read(notes_path)
    if notes:
        inj.set_notes(
            "【作業ノート】このプロジェクトで自分（このユーザー）が進めている作業の要点です。"
            f"`checkpoint` コマンドで更新されます。{core.notes_stamp(notes_path)}",
            notes, notes_path)
    if env != "local":
        inj.tail = CLOUD_GUIDE + (PROJECT_GUIDE if env == "project-thread" else "")

    text = inj.text()
    if not text:
        return 0
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": text,
    }}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"[post_compact_restore] {e}", file=sys.stderr)
        sys.exit(0)
