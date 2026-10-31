#!/usr/bin/env python3
"""
templates/checkpoint.md.in から、ツールごとの checkpoint コマンドを生成する。

  python3 tools/build_commands.py          … 生成して書き込む
  python3 tools/build_commands.py --check  … 生成結果とコミット済みのファイルが一致するか確かめる（テスト用）

雛形を直したら生成し直し、`bash install.sh team .` でこのリポジトリの導入物も同期する。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "templates" / "checkpoint.md.in"
OUTPUTS = {
    ROOT / "plugins" / "compact-restore" / "commands" / "checkpoint.md": {"TOOL": "Claude Code"},
}


def render(values):
    text = TEMPLATE.read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    return text


def main():
    check = "--check" in sys.argv[1:]
    stale = []
    for path, values in OUTPUTS.items():
        text = render(values)
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(path)
        else:
            path.write_text(text, encoding="utf-8")
            print(f"✓ {path.relative_to(ROOT)}")
    if stale:
        for p in stale:
            print(f"✗ 雛形と一致しません: {p.relative_to(ROOT)}（python3 tools/build_commands.py で生成し直す）")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
