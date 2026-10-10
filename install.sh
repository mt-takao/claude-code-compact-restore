#!/usr/bin/env bash
# 使い方:
#   bash install.sh plugin   [プロジェクトのパス]   … プラグインとして導入（推奨。Claude Code Projects・クラウドでも動く）
#   bash install.sh team     [プロジェクトのパス]   … フックを直接コミットしてチームで共有
#   bash install.sh personal [プロジェクトのパス]   … このプロジェクトで自分だけ（ローカルのみ）
#   bash install.sh global                          … 自分の全プロジェクト（ローカルのみ）
#   末尾に --uninstall を付けると取り除きます
set -euo pipefail
exec python3 "$(cd "$(dirname "$0")" && pwd)/installer.py" "$@"
