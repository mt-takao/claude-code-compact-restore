# claude-code-compact-restore — 開発ガイド

Claude Code の圧縮（`/compact`・自動圧縮）で作業文脈が失われないようにするフック・コマンド一式。
プラグイン（`compact-restore@mt-takao`）としても、フックを直接コミットする形でも導入できる。

これまでの経緯・設計判断・却下した案・未解決事項は [docs/development-log.md](docs/development-log.md) にある。
設計を変える前に必ず読むこと。

## 構成

```
.claude-plugin/marketplace.json        # マーケットプレイス（name: mt-takao）
plugins/compact-restore/
  .claude-plugin/plugin.json           # プラグイン（name: compact-restore、version を上げて配布）
  hooks/hooks.json                     # PreCompact / SessionStart を ${CLAUDE_PLUGIN_ROOT} 経由で登録
  scripts/pre_compact_snapshot.py      # フックの入口：圧縮直前に transcript と git から状態を退避
  scripts/post_compact_restore.py      # フックの入口：セッション開始・圧縮直後に注入。クラウド判定もここ
  scripts/compact_restore_core.py      # 共通部：保存先・git・スナップショットの書式・注入量の制御
  scripts/compact_restore_claude.py    # Claude Code の transcript の読み取り
  commands/checkpoint.md               # 作業ノート更新コマンド（templates/checkpoint.md.in から生成）
templates/CLAUDE.md.snippet            # 導入先 CLAUDE.md に追記する運用ルール（{CHECKPOINT} を置換）
templates/checkpoint.md.in             # checkpoint コマンドの雛形（python3 tools/build_commands.py で生成）
tools/capture_hook_input.py            # 採取用の仮フック（入力と記録を保存するだけ）
templates/project-instructions.md      # Claude Code Projects の「プロジェクト指示」用文例
installer.py / install.sh              # plugin / team / personal / global の4モード + --uninstall
tests/run_tests.sh                     # 自動テスト（Claude Code は起動せず入力を模擬）
CHANGELOG.md / CHANGELOG.en.md         # 版ごとの変更点（日英）
```

## 開発ルール

- 変更したら `bash tests/run_tests.sh` を実行し、全件 pass を確認する。`claude` コマンドがあれば `claude plugin validate .` も通す
- フックのスクリプトは Python 標準ライブラリのみ・Python 3.9 互換で書く（CI は 3.9 / 3.13 × Ubuntu / macOS）
- フックは失敗しても必ず exit 0（圧縮やセッション開始を妨げない）
- インストーラは冪等にする。既存の設定・CLAUDE.md・.gitignore を壊さずマージし、`--uninstall` で元に戻せること
- 作業ノート・スナップショット（`.claude/context/`）はどのモードでもコミットさせない
- README は日本語（README.md）と英語（README.en.md）の両方を更新する。挙動やインストーラを変えたら CHANGELOG.md と CHANGELOG.en.md にも追記する
- リポジトリは公開。社内のプロダクト名・個人情報・ローカルパスを含めない
- コミットの作者は Takao Mukai。プラグインの挙動を変えたら plugin.json の version を上げる
- このリポジトリ自体にも team モードで導入している（`.claude/hooks/`・`.claude/commands/`・`.claude/settings.json`）。`plugins/compact-restore/` のスクリプトやコマンドを変えたら `bash install.sh team .` を再実行して同期する（テストで一致を確認している）

## 現在の状態（2026-10-13 時点）

- `main`：v3.0.5。Projects のスレッドの発言・進捗表示、TaskCreate / TaskUpdate のタスクリストに対応済み
- v3.1.0（PR 作成中、2026-10-31）：注入量の制御、見出しの並べ替え、形式変化の警告、スクリプトの分割。続けて Codex CLI 対応（v3.2.0）を予定
- 実機で確認済み：4 つのモードすべて（`plugin` はローカル、`team` は Projects のスレッドの自動圧縮とローカルの手動 `/compact`、`personal` と `global` はローカル）、進捗表示とタスクリストの退避（docs/development-log.md の各「検証」の節）
- 次にやること・未解決事項は docs/development-log.md の「未解決・次にやること」を参照

## コンテキスト復元（圧縮対策）
- 作業ノート `.claude/context/working-notes.md` は、セッション開始時と圧縮後にフックで自動注入される
- 大きな区切り（設計確定・タスク完了・方針転換）のたびに `/checkpoint` で作業ノートを更新する
- 圧縮直後は「圧縮前スナップショット」と作業ノートを突き合わせてから再開し、食い違いは推測せずユーザーに確認する
- クラウドセッション（Claude Code Projects のスレッドを含む）では、途中経過をこまめに commit・push し、スレッドをまたいで必要な決定事項はプロジェクトメモリに記憶する
