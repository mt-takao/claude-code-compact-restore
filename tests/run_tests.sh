#!/usr/bin/env bash
# 自動テスト: bash tests/run_tests.sh
# 実際の Claude Code は起動せず、フックに渡される JSON と transcript を模擬して検証する。
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FIXTURE="$ROOT/tests/fixtures/transcript.jsonl"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
export GIT_AUTHOR_NAME=test GIT_AUTHOR_EMAIL=test@example.com
export GIT_COMMITTER_NAME=test GIT_COMMITTER_EMAIL=test@example.com

PASS=0; FAIL=0
check() {  # check "説明" <コマンド...>
  local desc="$1"; shift
  if "$@" >/dev/null 2>&1; then echo "  ✓ $desc"; PASS=$((PASS+1))
  else echo "  ✗ $desc"; FAIL=$((FAIL+1)); fi
}
new_repo() {
  rm -rf "$1"; mkdir -p "$1"; git -C "$1" init -q; git -C "$1" checkout -q -b feature/test
}
transcript_for() {  # プロジェクトパスを埋め込んだ transcript を作る
  sed "s#__PROJECT__#$1#g" "$FIXTURE" > "$WORK/t.jsonl"; echo "$WORK/t.jsonl"
}

echo "■ PreCompact: スナップショット抽出"
P="$WORK/snap"; new_repo "$P"; mkdir -p "$P/src"; echo x > "$P/src/Login.tsx"
T=$(transcript_for "$P")
echo "{\"transcript_path\":\"$T\",\"trigger\":\"manual\",\"custom_instructions\":\"決定事項を残す\"}" \
  | CLAUDE_PROJECT_DIR="$P" python3 "$ROOT/hooks/pre_compact_snapshot.py"
S="$P/.claude/context/latest-snapshot.md"
check "latest-snapshot.md が作られる"            test -f "$S"
check "履歴が snapshots/ に保存される"            test -n "$(ls "$P/.claude/context/snapshots")"
check "進行中タスクが [→] で記録される"          grep -q "\[→\] フォーム部品の置き換え" "$S"
check "ユーザー指示が記録される"                  grep -q "Secondaryにして" "$S"
check "tool_result・メタ・コマンドを除外する"      bash -c "! grep -qE 'Caveat|command-name' '$S'"
check "編集ファイルを相対パスで記録する"          grep -q "^- src/Login.tsx" "$S"
check "git ブランチを記録する"                    grep -q "feature/test" "$S"
check "/compact の focus を記録する"              grep -q "決定事項を残す" "$S"
check "壊れた入力でも exit 0（圧縮を止めない）"   bash -c "echo garbage | CLAUDE_PROJECT_DIR='$P' python3 '$ROOT/hooks/pre_compact_snapshot.py'"

echo "■ SessionStart: 注入内容"
printf '## ゴール\n- テスト用ノート\n' > "$P/.claude/context/working-notes.md"
check "compact: スナップショットを注入"   bash -c "echo '{\"source\":\"compact\"}' | CLAUDE_PROJECT_DIR='$P' python3 '$ROOT/hooks/post_compact_restore.py' | grep -q '圧縮前スナップショット'"
check "compact: 作業ノートも注入"         bash -c "echo '{\"source\":\"compact\"}' | CLAUDE_PROJECT_DIR='$P' python3 '$ROOT/hooks/post_compact_restore.py' | grep -q 'テスト用ノート'"
check "startup: 作業ノートのみ注入"       bash -c "out=\$(echo '{\"source\":\"startup\"}' | CLAUDE_PROJECT_DIR='$P' python3 '$ROOT/hooks/post_compact_restore.py'); echo \"\$out\" | grep -q 'テスト用ノート' && ! echo \"\$out\" | grep -q '圧縮前スナップショット'"
check "出力が正しい JSON"                 bash -c "echo '{\"source\":\"compact\"}' | CLAUDE_PROJECT_DIR='$P' python3 '$ROOT/hooks/post_compact_restore.py' | python3 -c 'import json,sys; json.load(sys.stdin)'"
E="$WORK/empty"; mkdir -p "$E"
check "何もなければ何も出力しない"        bash -c "[ -z \"\$(echo '{\"source\":\"startup\"}' | CLAUDE_PROJECT_DIR='$E' python3 '$ROOT/hooks/post_compact_restore.py')\" ]"

echo "■ install: team"
P="$WORK/team"; new_repo "$P"; mkdir -p "$P/.claude"
echo '{"permissions":{"allow":["Bash(npm test)"]},"hooks":{"Stop":[{"hooks":[{"type":"command","command":"echo done"}]}]}}' > "$P/.claude/settings.json"
printf '# Project\n\n## 既存ルール\n- keep me\n' > "$P/CLAUDE.md"
git -C "$P" add -A && git -C "$P" commit -qm init
bash "$ROOT/install.sh" team "$P" >/dev/null; bash "$ROOT/install.sh" team "$P" >/dev/null
check "既存の権限・フックを保持"          python3 -c "import json;d=json.load(open('$P/.claude/settings.json'));assert d['permissions'] and d['hooks']['Stop']"
check "再実行してもフックが重複しない"    python3 -c "import json;d=json.load(open('$P/.claude/settings.json'));assert len(d['hooks']['PreCompact'])==1 and len(d['hooks']['SessionStart'])==1"
check "既存の CLAUDE.md ルールを保持"      grep -q "keep me" "$P/CLAUDE.md"
check "運用ルールが1回だけ入る"            test "$(grep -c 'コンテキスト復元（圧縮対策）' "$P/CLAUDE.md")" = 1
check ".claude/context/ が gitignore される" bash -c "mkdir -p '$P/.claude/context' && touch '$P/.claude/context/x' && git -C '$P' check-ignore -q .claude/context/x"
bash "$ROOT/install.sh" team "$P" --uninstall >/dev/null
check "uninstall で自分のフックだけ消える" python3 -c "import json;d=json.load(open('$P/.claude/settings.json'));h=d['hooks'];assert 'Stop' in h and 'PreCompact' not in h and 'SessionStart' not in h"
check "uninstall で運用ルールが消える"     bash -c "! grep -q 'コンテキスト復元' '$P/CLAUDE.md' && grep -q 'keep me' '$P/CLAUDE.md'"

echo "■ install: personal"
P="$WORK/personal"; new_repo "$P"; echo "# shared" > "$P/CLAUDE.md"; git -C "$P" add -A && git -C "$P" commit -qm init
bash "$ROOT/install.sh" personal "$P" >/dev/null
check "git status に何も出ない"            test -z "$(git -C "$P" status --porcelain)"
check "settings.local.json に登録"         grep -q pre_compact_snapshot "$P/.claude/settings.local.json"
bash "$ROOT/install.sh" personal "$P" --uninstall >/dev/null
check "uninstall 後に空ファイルを残さない" bash -c "[ ! -e '$P/.claude/settings.local.json' ] && [ ! -e '$P/CLAUDE.local.md' ]"

echo "■ install: global"
FAKEHOME="$WORK/home"; mkdir -p "$FAKEHOME/.claude"; echo '{"model":"opus"}' > "$FAKEHOME/.claude/settings.json"
HOME="$FAKEHOME" XDG_CONFIG_HOME="$FAKEHOME/.config" bash "$ROOT/install.sh" global >/dev/null
check "既存のユーザー設定を保持"           grep -q '"model": "opus"' "$FAKEHOME/.claude/settings.json"
check "\$HOME 基準のパスで登録"            grep -q '\$HOME/.claude/hooks/pre_compact_snapshot.py' "$FAKEHOME/.claude/settings.json"
check "グローバル除外に .claude/context/"  grep -q "^.claude/context/$" "$FAKEHOME/.config/git/ignore"
P="$WORK/anyproj"; mkdir -p "$P"; T=$(transcript_for "$P")
check "任意のプロジェクトで退避できる"     bash -c "echo '{\"transcript_path\":\"$T\"}' | HOME='$FAKEHOME' CLAUDE_PROJECT_DIR='$P' sh -c 'python3 \"\$HOME/.claude/hooks/pre_compact_snapshot.py\"' && test -f '$P/.claude/context/latest-snapshot.md'"
HOME="$FAKEHOME" XDG_CONFIG_HOME="$FAKEHOME/.config" bash "$ROOT/install.sh" global --uninstall >/dev/null
check "uninstall で元の設定に戻る"         python3 -c "import json;assert json.load(open('$FAKEHOME/.claude/settings.json'))=={'model':'opus'}"

echo
echo "結果: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
