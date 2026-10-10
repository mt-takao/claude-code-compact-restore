# 開発ログ

claude.ai のチャット（2026-09-25〜10-11）で、この仕組みを設計・実装したときの経緯をまとめたもの。
Claude Code で作業を引き継ぐときの前提資料として使う。

## 着想

[koromo.io の記事](https://koromo.io/blog/claude-code-context-memory/)で解説されている
「PreCompact フックで圧縮前に退避し、圧縮後に再注入する」「構造化ノートを CLAUDE.md から読み込ませる」
という考え方を、実際に動く形にしたもの。

## バージョンの変遷

### v1（チャット内で作成、未公開）

- 3層構成
  - 作業ノート `.claude/context/working-notes.md` を CLAUDE.md から `@import`
  - PreCompact フックが transcript と git からスナップショットを退避
  - SessionStart（matcher: `compact`）フックがスナップショットを再注入
- スナップショットに残すもの：TodoWrite のタスクリスト、直近のユーザー指示（tool_result・メタ・コマンド出力・圧縮サマリーは除外）、編集ファイル、git ブランチと未コミット変更、圧縮直前の Claude の発言、/compact の focus
- 抽出は LLM を使わず機械的に行う。意味の要約は作業ノート（Claude 自身が書く）に任せる、という役割分担

### v2（GitHub で公開した版）

- **作業ノートを個人のものに変更**：v1 はノートをコミットしてチーム共有する前提だったが、ノートは「自分がどこまで進めたか」なので、共有すると他人の作業状態が注入されてしまう
- **ノートの読み込みを @import から SessionStart フックに変更**：global（`~/.claude`）導入時に、プロジェクトごとのノートを読めるようにするため
- インストーラを3モード化：`team` / `personal` / `global`、`--uninstall`、v1 からの移行（コミット済みノートの追跡解除）
- 公開用に再構成：MIT ライセンス、GitHub Actions（Ubuntu・macOS × Python 3.9・3.13）、自動テスト 29 項目、日英 README

### v3（ブランチ `claude/project-thread-qg6z1b`、PR でレビュー中）

Claude Code Projects（プロジェクト会話＝コーディネーター + スレッド＝クラウドセッション）では、圧縮は自動のみで手動の `/compact` は使わない。ドキュメントを確認して見つかった問題と対応：

| 問題 | 対応 |
|---|---|
| リポジトリが複数のプロジェクトでは、リポジトリの `.claude/settings.json` のフックがスレッドに適用されない（プラグインのフックは適用される） | プラグイン化。`install.sh plugin` でリポジトリの settings.json に `extraKnownMarketplaces` と `enabledPlugins` を登録 |
| `personal` / `global` は `~/.claude` や `settings.local.json` を使うのでクラウドに届かない | README で「ローカルのみ」と明記。Projects では `plugin` を使う |
| `.claude/context/` は VM 内だけでスレッド間共有されず、VM 再作成で消える | SessionStart がクラウド（`CLAUDE_CODE_REMOTE=true`）と Projects スレッド（`/mnt/project-files` の有無）を判定し、「こまめに push」「スレッドをまたぐ決定はプロジェクトメモリへ」と案内を注入 |
| コーディネーターにはフックが効かない | `templates/project-instructions.md`（プロジェクト指示の文例）で、プロジェクトメモリへの記録ルールを渡す |

その他：checkpoint コマンドが Projects では push とプロジェクトメモリ更新も行う。スナップショットにクラウドセッションの URL（`CLAUDE_CODE_REMOTE_SESSION_ID` から生成）を記録。`plugin` と `team` は切り替え式で二重登録しない。テスト 45 項目。

## 確定した設計判断

- フックは常に exit 0。壊れた transcript でも圧縮を止めない
- スナップショットと作業ノートは `.claude/context/` に置き、どのモードでも git に載せない（ユーザー指示の原文を含むため）
- 注入量の上限：スナップショット 12,000 文字、ノート 6,000 文字。スナップショット履歴は直近 20 件
- 圧縮サマリーと食い違う場合はスナップショットの具体的記録を優先し、推測せずユーザーに確認するよう注入文で指示する
- コマンド名：プラグイン導入時は `/compact-restore:checkpoint`、直接導入時は `/checkpoint`

## 却下した案

- **作業ノートをチームで共有する**：個人の進捗が他人のセッションに注入されるため（v2 で撤回）
- **CLAUDE.md の `@import` でノートを読む**：global 導入時にプロジェクトごとのノートを指せないため（v2 で撤回）
- **クラウドでスナップショットを作業ブランチにコミットする**：PR に作業ログが混ざるため。スレッドをまたぐ情報はプロジェクトメモリに任せる
- **`/hooks` で登録確認する手順（Desktop の Code タブ）**：Code タブでは使えないため、Claude に settings.json のフック一覧を聞く方法にした

## 利用環境ごとの注意（調査結果）

- Claude Desktop の Code タブ：フックは CLI と同じ設定で動く。`/compact` は使えるが `/hooks` は使えない。統合ターミナル（Ctrl+`）でインストールできる
- Cowork タブ：settings.json のフックが発火しないという報告がある
- GUI から起動したアプリでは PATH が違うことがあり、`python3` が見つからないとフックが黙って失敗する。その場合は settings.json の `python3` を絶対パスにする
- リポジトリの settings.json で宣言したマーケットプレイスは、フォルダの信頼を承認した後に登録される

## 未解決・次にやること

1. **v3 のマージ**：claude.ai のチャットからは push できなかった（403）ため、パッチを Claude Code Projects のスレッドから適用して PR にした。レビューしてマージする
2. **実環境での検証**：実際の Projects スレッドで、自動圧縮をまたいで復元できるかは未確認。Desktop の Code タブ（Local）での `/compact` 復元も、実機での確認はユーザー側で行う
3. **マージ前のプラグイン試用**：settings.json は GitHub の main からプラグインを取得するため、マージ前は `/plugin marketplace add <ローカルのリポジトリ>` で入れる
4. transcript の形式は Claude Code の内部仕様なので、将来の変更で抽出が壊れていないか定期的に確認する
5. Windows（WSL 以外）では `python3` を `python` / `py` に書き換える必要がある。インストーラでの自動判定は未対応

## 参考

- [Hooks reference](https://code.claude.com/docs/en/hooks)
- [Claude Code Projects](https://code.claude.com/docs/ja/claude-projects)
- [クラウド環境を設定する](https://code.claude.com/docs/ja/cloud-environments)
- [Create a marketplace](https://code.claude.com/docs/en/plugin-marketplaces) / [Plugin components](https://code.claude.com/docs/en/plugins/components) / [Manage plugins for your organization](https://code.claude.com/docs/en/plugins/org)
