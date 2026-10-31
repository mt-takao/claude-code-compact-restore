#!/usr/bin/env python3
"""
PreCompact hook: 圧縮（/compact・auto-compact）の直前に作業状態をファイルへ退避する。

退避先:
  .claude/context/snapshots/<timestamp>.md   … 履歴（直近 KEEP 件を保持）
  .claude/context/latest-snapshot.md         … 圧縮後に再注入される最新版

抽出する情報（LLMを使わず transcript から機械的に取れるもの）は compact_restore_claude.py、
スナップショットの書式と git の状態は compact_restore_core.py を参照。
"""
import os
import sys

sys.dont_write_bytecode = True  # 導入先の hooks フォルダに __pycache__ を作らない
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    import compact_restore_claude as transcript
    import compact_restore_core as core

    hook = core.read_hook_input()
    project_dir = core.project_root(hook)
    data = transcript.read(hook.get("transcript_path"), project_dir)
    md = core.render_snapshot(hook, data, project_dir)
    core.write_snapshot(core.context_dir(project_dir), md)
    return 0  # 失敗しても圧縮自体は止めない


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"[pre_compact_snapshot] {e}", file=sys.stderr)
        sys.exit(0)
