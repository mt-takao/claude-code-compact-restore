#!/usr/bin/env bash
# 使い方:
#   bash install.sh team     [プロジェクトのパス]   … チームで共有（コミットする）
#   bash install.sh personal [プロジェクトのパス]   … このプロジェクトで自分だけ
#   bash install.sh global                          … 自分の全プロジェクト
#   末尾に --uninstall を付けると取り除きます
set -euo pipefail
exec python3 "$(cd "$(dirname "$0")" && pwd)/installer.py" "$@"
