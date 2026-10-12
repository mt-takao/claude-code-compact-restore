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
  scripts/pre_compact_snapshot.py      # 圧縮直前に transcript と git から状態を退避
  scripts/post_compact_restore.py      # セッション開始・圧縮直後に注入。クラウド判定もここ
  commands/checkpoint.md               # 作業ノート更新コマンド
templates/CLAUDE.md.snippet            # 導入先 CLAUDE.md に追記する運用ルール（{CHECKPOINT} を置換）
templates/project-instructions.md      # Claude Code Projects の「プロジェクト指示」用文例
installer.py / install.sh              # plugin / team / personal / global の4モード + --uninstall
tests/run_tests.sh                     # 自動テスト（Claude Code は起動せず入力を模擬）
```

## 開発ルール

- 変更したら `bash tests/run_tests.sh` を実行し、全件 pass を確認する。`claude` コマンドがあれば `claude plugin validate .` も通す
- フックのスクリプトは Python 標準ライブラリのみ・Python 3.9 互換で書く（CI は 3.9 / 3.13 × Ubuntu / macOS）
- フックは失敗しても必ず exit 0（圧縮やセッション開始を妨げない）
- インストーラは冪等にする。既存の設定・CLAUDE.md・.gitignore を壊さずマージし、`--uninstall` で元に戻せること
- 作業ノート・スナップショット（`.claude/context/`）はどのモードでもコミットさせない
- README は日本語（README.md）と英語（README.en.md）の両方を更新する
- リポジトリは公開。社内のプロダクト名・個人情報・ローカルパスを含めない
- コミットの作者は Takao Mukai。プラグインの挙動を変えたら plugin.json の version を上げる

## 現在の状態（2026-10-12 時点）

- `main`：v3.0.5。Projects のスレッドの発言・進捗表示、TaskCreate / TaskUpdate のタスクリストに対応済み
- 実機で確認済み：`plugin` モード（ローカル）、`team` モード（Projects のスレッドの自動圧縮、ローカルの手動 `/compact`）、進捗表示とタスクリストの退避（docs/development-log.md の「Projects スレッドでの検証」「ローカルでのタスクリストの検証」）
- 次にやること・未解決事項は docs/development-log.md の「未解決・次にやること」を参照
