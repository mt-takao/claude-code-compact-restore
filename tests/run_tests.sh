#!/usr/bin/env bash
# 自動テスト: bash tests/run_tests.sh
# 実際の Claude Code は起動せず、フックに渡される JSON と transcript を模擬して検証する。
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOKS="$ROOT/plugins/compact-restore/scripts"
PLUGIN="$ROOT/plugins/compact-restore"
# テスト自体がクラウドセッションで走ってもローカル扱いで検証する
unset CLAUDE_CODE_REMOTE CLAUDE_CODE_REMOTE_SESSION_ID
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
  | CLAUDE_PROJECT_DIR="$P" python3 "$HOOKS/pre_compact_snapshot.py"
S="$P/.claude/context/latest-snapshot.md"
check "latest-snapshot.md が作られる"            test -f "$S"
check "履歴が snapshots/ に保存される"            test -n "$(ls "$P/.claude/context/snapshots")"
check "進行中タスクが [→] で記録される"          grep -q "\[→\] フォーム部品の置き換え" "$S"
check "ユーザー指示が記録される"                  grep -q "Secondaryにして" "$S"
check "tool_result・メタ・コマンドを除外する"      bash -c "! grep -qE 'Caveat|command-name' '$S'"
check "編集ファイルを相対パスで記録する"          grep -q "^- src/Login.tsx" "$S"
check "一時フォルダの作業ファイルは記録しない"    bash -c "! grep -q 'gen_pages.py' '$S'"
check "更新したメモリは別の見出しに記録する"      bash -c "sed -n '/^## このセッションで更新したメモリ/,/^\$/p' '$S' | grep -q 'memory/team/silo/decisions.md' && ! sed -n '/^## このセッションで編集したファイル/,/^\$/p' '$S' | grep -q 'decisions.md'"
check "プロジェクト外の作業ファイルは残す"        bash -c "sed -n '/^## このセッションで編集したファイル/,/^\$/p' '$S' | grep -q 'other-repo/api/schema.ts'"
check "git ブランチを記録する"                    grep -q "feature/test" "$S"
check "/compact の focus を記録する"              grep -q "決定事項を残す" "$S"
check "壊れた入力でも exit 0（圧縮を止めない）"   bash -c "echo garbage | CLAUDE_PROJECT_DIR='$P' python3 '$HOOKS/pre_compact_snapshot.py'"

echo "■ SessionStart: 注入内容"
printf '## ゴール\n- テスト用ノート\n' > "$P/.claude/context/working-notes.md"
check "compact: スナップショットを注入"   bash -c "echo '{\"source\":\"compact\"}' | CLAUDE_PROJECT_DIR='$P' python3 '$HOOKS/post_compact_restore.py' | grep -q '圧縮前スナップショット'"
check "compact: 作業ノートも注入"         bash -c "echo '{\"source\":\"compact\"}' | CLAUDE_PROJECT_DIR='$P' python3 '$HOOKS/post_compact_restore.py' | grep -q 'テスト用ノート'"
check "startup: 作業ノートのみ注入"       bash -c "out=\$(echo '{\"source\":\"startup\"}' | CLAUDE_PROJECT_DIR='$P' python3 '$HOOKS/post_compact_restore.py'); echo \"\$out\" | grep -q 'テスト用ノート' && ! echo \"\$out\" | grep -q '圧縮前スナップショット'"
check "出力が正しい JSON"                 bash -c "echo '{\"source\":\"compact\"}' | CLAUDE_PROJECT_DIR='$P' python3 '$HOOKS/post_compact_restore.py' | python3 -c 'import json,sys; json.load(sys.stdin)'"
E="$WORK/empty"; mkdir -p "$E"
check "何もなければ何も出力しない"        bash -c "[ -z \"\$(echo '{\"source\":\"startup\"}' | CLAUDE_PROJECT_DIR='$E' python3 '$HOOKS/post_compact_restore.py')\" ]"

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
printf '\nnode_modules/\n' >> "$P/.gitignore"; cp "$P/.gitignore" "$WORK/gitignore.before"
printf '\n## 後から足した節\n- after\n' >> "$P/CLAUDE.md"; cp "$P/CLAUDE.md" "$WORK/claude-md.before"
bash "$ROOT/install.sh" team "$P" >/dev/null
check "再実行しても .gitignore の並びを変えない" cmp -s "$P/.gitignore" "$WORK/gitignore.before"
check "再実行しても CLAUDE.md の節の並びを変えない" cmp -s "$P/CLAUDE.md" "$WORK/claude-md.before"
bash "$ROOT/install.sh" team "$P" --uninstall >/dev/null
check "uninstall で後から足した節は残す"   bash -c "grep -q '^- after\$' '$P/CLAUDE.md' && grep -q '^## 後から足した節\$' '$P/CLAUDE.md'"
check "uninstall で後から足した行は残す"   bash -c "grep -q '^node_modules/\$' '$P/.gitignore' && ! grep -q 'compact-restore-kit' '$P/.gitignore'"
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

echo "■ クラウドセッション・Projects スレッド"
P="$WORK/cloud"; new_repo "$P"; T=$(transcript_for "$P")
echo "{\"transcript_path\":\"$T\",\"trigger\":\"auto\"}" \
  | CLAUDE_CODE_REMOTE=true CLAUDE_CODE_REMOTE_SESSION_ID=cse_abc123 CLAUDE_PROJECT_DIR="$P" python3 "$HOOKS/pre_compact_snapshot.py"
check "スナップショットに元セッションの URL"   grep -q "https://claude.ai/code/session_abc123" "$P/.claude/context/latest-snapshot.md"
echo "{\"transcript_path\":\"$ROOT/tests/fixtures/projects-transcript.jsonl\",\"trigger\":\"auto\"}" \
  | CLAUDE_PROJECT_DIR="$P" python3 "$HOOKS/pre_compact_snapshot.py"
S="$P/.claude/context/latest-snapshot.md"
check "Projects: 通知の包みから発言だけを記録"   bash -c "grep -q 'Taro: 見出しの色は <h2> だけ変えて' '$S' && ! grep -qE '<wake|<project|cmsg_' '$S'"
check "Projects: 人間以外の通知は記録しない"     bash -c "! grep -qE 'reaction|別セッションの報告' '$S'"
check "Projects: 直前の発言に返信の本文を使う"   grep -q "h2 の色を変えました" "$S"
run_start() {  # run_start <remote> <project-files-dir>
  echo '{"source":"startup"}' | CLAUDE_CODE_REMOTE="$1" COMPACT_RESTORE_PROJECT_FILES="$2" CLAUDE_PROJECT_DIR="$WORK/empty" python3 "$HOOKS/post_compact_restore.py"
}
export -f run_start; export HOOKS WORK
mkdir -p "$WORK/pf"
check "クラウド: commit/push の案内を注入"         bash -c "run_start true '$WORK/none' | grep -q 'commit して push'"
check "クラウド（Projects 以外）: メモリ案内なし"  bash -c "! run_start true '$WORK/none' | grep -q 'プロジェクトメモリ'"
check "Projects スレッド: プロジェクトメモリ案内"  bash -c "run_start true '$WORK/pf' | grep -q 'プロジェクトメモリ'"
check "ローカル: 案内を出さない"                   bash -c "[ -z \"\$(run_start '' '$WORK/pf')\" ]"

echo "■ プラグイン構成"
check "plugin.json と marketplace.json が正しい JSON" python3 -c "import json;json.load(open('$PLUGIN/.claude-plugin/plugin.json'));json.load(open('$ROOT/.claude-plugin/marketplace.json'))"
check "マーケットプレイスの名前が一致"   python3 -c "import json;m=json.load(open('$ROOT/.claude-plugin/marketplace.json'));p=json.load(open('$PLUGIN/.claude-plugin/plugin.json'));assert m['plugins'][0]['name']==p['name']=='compact-restore' and m['name']=='mt-takao'"
check "hooks.json のスクリプトが存在"     python3 -c "
import json,re,os
h=json.load(open('$PLUGIN/hooks/hooks.json'))['hooks']
cmds=[x['command'] for g in h.values() for e in g for x in e['hooks']]
assert len(cmds)==2
for c in cmds:
    path=re.search(r'\\$\{CLAUDE_PLUGIN_ROOT\}/(\S+?)\"',c).group(1); assert os.path.isfile(os.path.join('$PLUGIN',path)), path"
if command -v claude >/dev/null 2>&1; then
  check "claude plugin validate（マーケットプレイス）" bash -c "claude plugin validate '$ROOT' | grep -q 'Validation passed'"
fi

echo "■ install: plugin"
P="$WORK/plugin"; new_repo "$P"; mkdir -p "$P/.claude"
echo '{"permissions":{"allow":["Bash(npm test)"]}}' > "$P/.claude/settings.json"
bash "$ROOT/install.sh" team "$P" >/dev/null           # team から切り替えるケース
bash "$ROOT/install.sh" plugin "$P" >/dev/null; bash "$ROOT/install.sh" plugin "$P" >/dev/null
check "マーケットプレイスとプラグインを登録" python3 -c "import json;d=json.load(open('$P/.claude/settings.json'));assert d['enabledPlugins']=={'compact-restore@mt-takao':True} and d['extraKnownMarketplaces']['mt-takao']['source']=={'source':'github','repo':'mt-takao/claude-code-compact-restore'}"
check "直接登録のフックを外す（二重防止）"   python3 -c "import json;d=json.load(open('$P/.claude/settings.json'));assert 'hooks' not in d and d['permissions']"
check "team で置いたファイルを片付ける"      bash -c "[ ! -e '$P/.claude/hooks/pre_compact_snapshot.py' ] && [ ! -e '$P/.claude/commands/checkpoint.md' ]"
check "運用ルールはプラグインのコマンド名"   bash -c "grep -q '/compact-restore:checkpoint' '$P/CLAUDE.md' && [ \"\$(grep -c 'コンテキスト復元（圧縮対策）' '$P/CLAUDE.md')\" = 1 ]"
check ".claude/context/ が gitignore される"  bash -c "mkdir -p '$P/.claude/context' && touch '$P/.claude/context/x' && git -C '$P' check-ignore -q .claude/context/x"
bash "$ROOT/install.sh" team "$P" >/dev/null
check "plugin → team に戻すとプラグイン設定が消える" python3 -c "import json;d=json.load(open('$P/.claude/settings.json'));assert 'enabledPlugins' not in d and 'PreCompact' in d['hooks']"
bash "$ROOT/install.sh" plugin "$P" >/dev/null; bash "$ROOT/install.sh" plugin "$P" --uninstall >/dev/null
check "uninstall で元の設定に戻る"           python3 -c "import json;assert json.load(open('$P/.claude/settings.json'))=={'permissions':{'allow':['Bash(npm test)']}}"

echo
echo "結果: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
