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
| 配布しやすくしたい | プラグイン化。`install.sh plugin` でリポジトリの settings.json に `extraKnownMarketplaces` と `enabledPlugins` を登録（ローカルのセッション向け） |
| `personal` / `global` / `plugin` はクラウドに届かない（`~/.claude` や `settings.local.json` は VM にない。リポジトリで有効化したプラグインもクラウドセッションはインストールしない） | README で「ローカルのみ」と明記。Projects では `team` を使う |
| リポジトリが複数のプロジェクトでは、リポジトリの `.claude/settings.json` のフックもプラグインもスレッドに適用されない | 非対応と明記。プロジェクトメモリとプロジェクト指示で文脈を残す |
| `.claude/context/` は VM 内だけでスレッド間共有されず、VM 再作成で消える | SessionStart がクラウド（`CLAUDE_CODE_REMOTE=true`）と Projects スレッド（`/mnt/project-files` の有無）を判定し、「こまめに push」「スレッドをまたぐ決定はプロジェクトメモリへ」と案内を注入 |
| コーディネーターにはフックが効かない | `templates/project-instructions.md`（プロジェクト指示の文例）で、プロジェクトメモリへの記録ルールを渡す |

その他：checkpoint コマンドが Projects では push とプロジェクトメモリ更新も行う。スナップショットにクラウドセッションの URL（`CLAUDE_CODE_REMOTE_SESSION_ID` から生成）を記録。`plugin` と `team` は切り替え式で二重登録しない。テスト 45 項目。

## 確定した設計判断

- フックは常に exit 0。壊れた transcript でも圧縮を止めない
- スナップショットと作業ノートは `.claude/context/` に置き、どのモードでも git に載せない（ユーザー指示の原文を含むため）
- 注入量の上限：スナップショット 12,000 文字、ノート 6,000 文字。スナップショット履歴は直近 20 件
- 圧縮サマリーと食い違う場合はスナップショットの具体的記録を優先し、推測せずユーザーに確認するよう注入文で指示する
- コマンド名：プラグイン導入時は `/compact-restore:checkpoint`、直接導入時は `/checkpoint`
- Projects・クラウドセッション向けは `team` モード。公式ドキュメント（cloud-environments の「What carries over from your setup」）に、クラウドセッションはリポジトリの `enabledPlugins` / `extraKnownMarketplaces` のプラグインをインストールせず、リポジトリ複数のセッションはリポジトリのフックを読まないと明記されているため（2026-10-11 に確認）

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

## Projects スレッドでの検証（2026-10-11）

`team` モードを入れたリポジトリを 1 つだけ追加したプロジェクトのスレッドで確認した。

- セッション開始時に、クラウドの案内と Projects スレッド向けの案内（プロジェクトメモリへの記憶）が注入された
- 自動圧縮の直前にスナップショットが作られた（`trigger: auto`、「元のセッション」の URL あり）。圧縮後、スレッドは圧縮直前の作業と判断待ちの論点を正しく答えた
- 見つかった問題：Projects では人間の発言が通知データ（`<wake>` の XML）に包まれて届くため、スナップショットの「直近のユーザー指示」に包みがそのまま入り、600 文字の枠を圧迫していた。v3.0.1 で発言の本文と送り手だけを取り出すように直した。他のセッションやワーカーからの通知は記録しない。あわせて、ユーザーに見える返信は返信ツールの引数にあるため、「圧縮直前の Claude の発言」にはその本文を使う
- `team` モードはスクリプトをコピーして導入するため、更新を反映するには導入先で `install.sh team .` を再実行してコミットする
- v3.0.1 を同じスレッドに取り込んで再確認した（2026-10-11、2 回目の自動圧縮）。「直近のユーザー指示」は「送り手: 本文」の形になり、スナップショットは約 7.4KB から約 2.3KB に減った
- 見つかった問題：「編集したファイル」17 件のうち 8 件がプロジェクト外だった。一時フォルダの作業用スクリプト（scratchpad）と、プロジェクトメモリのファイルが混ざっていた。v3.0.2 で、一時フォルダと scratchpad のファイルは記録せず、メモリのファイルは「更新したメモリ」として別の見出しに分けた。それ以外のプロジェクト外のファイル（別のリポジトリなど）は、これまでどおり絶対パスで残す
- `install.sh team .` の再実行で、`.gitignore` の除外ブロックが末尾へ移動して空行が残ることがあった（ブロックの後ろにほかの行がある場合）。インストーラを、既存のブロックは同じ位置で差し替えるように直した
- 同じ性質が CLAUDE.md の運用ルールにもあった（再インストールで節が末尾へ移動し、後ろに足した節と順序が入れ替わる）。こちらも、既存の節は同じ位置で差し替えるように直した。`plugin` と `team` の切り替えでコマンド名を書き換えるときも位置は変わらない
- v3.0.2 を同じスレッドに取り込んで再確認した（2026-10-12、3 回目の自動圧縮、約 1.8KB）。「編集したファイル」はリポジトリ内のファイルだけになり、scratchpad のスクリプトは入らず、メモリのファイル 5 件は「更新したメモリ」に分かれた。未コミットの変更（7 件）も記録され、圧縮後のスレッドはその内容どおりに作業を続けた
- 仕様として残る点：「編集したファイル」は Edit / Write ツールでの編集だけを記録し、シェル経由で書き換えたファイルは入らない。未コミットの変更の一覧で補える
- 見つかった問題：Projects のスレッドは TodoWrite ではなく進捗表示（チェックリスト）を使うため、タスクリストが退避されなかった。「圧縮直前の発言」も作業開始時の返信のままで、進み具合が古かった。v3.0.3 で、最新の進捗表示を「スレッドの進捗表示」としてスナップショットに記録するようにした
- v3.0.4 を同じスレッドに取り込んで再確認した（2026-10-12、4 回目の自動圧縮、約 3.3KB）。「スレッドの進捗表示」に、圧縮の時点のチェックリスト（1 つ目が作業中、残り 3 つが未着手）が入り、直前の指示や発言とも一致した
- 見つかった問題：Projects のスレッドはタスクリストのツールを使わないため、「進行中のタスクリスト」が毎回「（タスクリストの記録なし）」になっていた。v3.0.5 で、進捗表示があるときはこの欄を出さないようにした

## ローカルでのタスクリストの検証（2026-10-12）

- `team` モードのフックは、ローカルのセッションの手動 `/compact` でも動いた
- 確認した環境（Claude Code 2.1.296）のセッションには、既定ではタスクを管理するツールがなかった。そのため、スナップショットのタスクリストは空だった
- `CLAUDE_CODE_ENABLE_TODO_TOOLS=1` を付けて起動すると TaskCreate / TaskUpdate が、さらに `CLAUDE_CODE_ENABLE_TASKS=0` を付けると TodoWrite が使える（公式ドキュメントで確認したものではなく、起動して確かめた結果。将来変わる可能性がある）
- TaskCreate / TaskUpdate のタスクリストは、これまでスナップショットに入らなかった。v3.0.4 で対応した。TaskCreate はタスクの ID が結果（tool_result）側にしか入らないため、呼び出しと結果を突き合わせて ID を得る。TaskUpdate の状態と件名の変更を積み重ね、`deleted` は一覧から外す。作成の記録が見つからないタスクは「タスク #番号」として残す
- 記録がないときの文言を「（TodoWrite の記録なし）」から「（タスクリストの記録なし）」に変えた
- v3.0.4 を `team` モードの f1-scroll-snap に入れ、`CLAUDE_CODE_ENABLE_TODO_TOOLS=1` のローカルのセッションで確認した（2026-10-12、手動 `/compact`）。TaskCreate 3 回・TaskUpdate 2 回のタスクリストが `[x]`・`[x]`・`[ ]` で記録された

## 未解決・次にやること

1. **実環境での検証（未確認の残り）**：`personal` / `global` モードの実機確認。古い方式の TodoWrite は自動テストのみ（いまの Claude Code では既定で使われない）
2. transcript の形式は Claude Code の内部仕様なので、将来の変更で抽出が壊れていないか定期的に確認する
3. Windows（WSL 以外）では `python3` を `python` / `py` に書き換える必要がある。インストーラでの自動判定は未対応

## 参考

- [Hooks reference](https://code.claude.com/docs/en/hooks)
- [Claude Code Projects](https://code.claude.com/docs/ja/claude-projects)
- [クラウド環境を設定する](https://code.claude.com/docs/ja/cloud-environments)
- [Create a marketplace](https://code.claude.com/docs/en/plugin-marketplaces) / [Plugin components](https://code.claude.com/docs/en/plugins/components) / [Manage plugins for your organization](https://code.claude.com/docs/en/plugins/org)
