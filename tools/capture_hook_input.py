#!/usr/bin/env python3
"""
採取用の仮フック: フックに渡された入力と、その時点の記録（transcript / rollout）を保存するだけ。
Codex 対応を作る前に、実際の入力と記録の形を確かめるために使う。何も出力せず、必ず exit 0 で終わる。

保存先: ~/compact-restore-capture/<日時>-<イベント名>/
        （環境変数 COMPACT_RESTORE_CAPTURE_DIR で変更可）
  input.json    … フックに渡された JSON（そのまま）
  env.json      … 名前に CODEX / CLAUDE / PLUGIN を含む環境変数と、作業フォルダ
  transcript.*  … transcript_path の指す記録のコピー（あれば）

保存したファイルには会話の原文が含まれます。共有する前に、見せたくない部分を消してください。

Codex での使い方（~/.codex/hooks.json。パスはこのリポジトリを置いた場所に合わせる）:
{
  "hooks": {
    "PreCompact":   [{ "hooks": [{ "type": "command", "command": "python3 /path/to/claude-code-compact-restore/tools/capture_hook_input.py" }] }],
    "PostCompact":  [{ "hooks": [{ "type": "command", "command": "python3 /path/to/claude-code-compact-restore/tools/capture_hook_input.py" }] }],
    "SessionStart": [{ "hooks": [{ "type": "command", "command": "python3 /path/to/claude-code-compact-restore/tools/capture_hook_input.py" }] }]
  }
}
登録後、Codex の /hooks で承認してから使う。採取が終わったら登録を外す。
"""
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path


def main():
    raw = sys.stdin.read()
    try:
        hook = json.loads(raw)
    except Exception:
        hook = {}
    event = str(hook.get("hook_event_name") or "unknown")
    base = Path(os.environ.get("COMPACT_RESTORE_CAPTURE_DIR") or Path.home() / "compact-restore-capture")
    out = base / f"{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}-{event}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "input.json").write_text(raw, encoding="utf-8")
    env = {k: v for k, v in os.environ.items()
           if any(s in k.upper() for s in ("CODEX", "CLAUDE", "PLUGIN"))
           and not any(s in k.upper() for s in ("KEY", "TOKEN", "SECRET", "PASSWORD"))}
    env["(cwd)"] = os.getcwd()
    (out / "env.json").write_text(json.dumps(env, indent=2, ensure_ascii=False), encoding="utf-8")
    src = hook.get("transcript_path")
    if src and Path(src).is_file():
        shutil.copy2(src, out / ("transcript" + "".join(Path(src).suffixes)))
    return 0


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[capture_hook_input] {e}", file=sys.stderr)
    sys.exit(0)
