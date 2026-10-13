# claude-code-compact-restore

[![test](https://github.com/mt-takao/claude-code-compact-restore/actions/workflows/test.yml/badge.svg)](https://github.com/mt-takao/claude-code-compact-restore/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

日本語 | [English](README.en.md)

Claude Code で `/compact` や自動圧縮（auto-compact）が走っても、作業の文脈を失わないためのフックとコマンドのセットです。
ローカルのセッションに加え、自動圧縮のみの [Claude Code Projects](https://code.claude.com/docs/ja/claude-projects) のスレッド（クラウドセッション、リポジトリ 1 つの場合）でも、`team` モードで動きます。

最新版は v3.0.5 です。v1 からの変更点は [変更履歴](#変更履歴) を参照してください。

> **English summary:** Hooks and a slash command that preserve working context across Claude Code compaction. A `PreCompact` hook snapshots your task list, recent prompts, edited files and git state; a `SessionStart` hook re-injects that snapshot plus your personal working notes after compaction. Works in local sessions, and in Claude Code Projects threads with one repository (cloud sessions, auto-compact only) via `team` mode. Install as a plugin (`bash install.sh plugin`) or as plain hooks (`team|personal|global`). Requires Python 3.9+.

## なぜ必要か

圧縮後の要約では、「どのタスクが途中か」「どのファイルを触ったか」「なぜその案を却下したか」といった具体的な情報が抜け落ちがちです。このツールは、次の2つを組み合わせて圧縮後の文脈を補います。

- **機械的な退避**：圧縮の直前に、会話記録と git から事実を抜き出して保存する
- **構造化ノート**：Claude 自身に、意図や判断の理由をノートとして書かせておく

## 仕組み

| 部品 | いつ動くか | 何をするか |
|---|---|---|
| `checkpoint` コマンド | 作業の区切りで手動実行 | 作業ノート `.claude/context/working-notes.md` を更新する（ゴール・決定事項・却下案・現在地・次の一手・未解決の論点）。プラグイン導入時は `/compact-restore:checkpoint`、それ以外は `/checkpoint` |
| `PreCompact` フック | 圧縮の直前に自動 | タスクリスト（TodoWrite、または TaskCreate / TaskUpdate。Projects のスレッドでは進捗表示）・直近のユーザー指示・編集ファイル（一時フォルダの作業ファイルは除く）・更新したメモリ・git 状態・直前の発言をスナップショットとして退避する |
| `SessionStart` フック | セッション開始時と圧縮直後に自動 | 作業ノートを注入する。圧縮直後はスナップショットもあわせて注入する。クラウドセッションでは記録先の案内も注入する |

作業ノートとスナップショットは**個人のもの**なので、どの導入モードでも git にはコミットされません。

### スナップショットの例

圧縮の直前に `.claude/context/latest-snapshot.md` に保存され、圧縮の直後に注入されます（履歴は `.claude/context/snapshots/`）。
記録がない項目（タスクリスト・メモリ・git など）は省略されるか「（なし）」と表示されます。

````markdown
# 圧縮前スナップショット（2026-10-12 21:04:13 / trigger: manual）

/compact の focus 指定: 決定事項を残す

## 進行中のタスクリスト
- [x] 設定ファイルの読み込みを直す
- [→] テストを追加する
- [ ] README を更新する

## 直近のユーザー指示（古い→新しい）
1. 設定ファイルが無いときに落ちるので直してください
2. テストも追加して

## このセッションで編集したファイル（最後に触った順で末尾）
- src/config.py
- tests/test_config.py

## Git 状態
- ブランチ: `fix-config`
- 未コミットの変更:
```
 M src/config.py
?? tests/test_config.py
```

## 圧縮直前の Claude の発言（どこまで進んでいたか）
設定ファイルが無い場合は既定値を使うように直しました。次にテストを追加します。
````

- クラウドセッションでは、見出しの下に「元のセッション」の URL が入ります
- Projects のスレッドでは、タスクリストの代わりに「スレッドの進捗表示」（✓ 完了 / ✱ 作業中 / ○ 未着手）が入り、ユーザー指示は「送り手: 本文」の形で記録されます
- プロジェクト外のメモリのファイルを更新した場合は「このセッションで更新したメモリ」が加わります

## 導入

要件は Python 3.9 以上（標準ライブラリのみ）です。git はなくても動きますが、あると git 状態の記録と除外設定が有効になります。

```bash
git clone https://github.com/mt-takao/claude-code-compact-restore.git ~/tools/claude-code-compact-restore
cd /path/to/your-project
bash ~/tools/claude-code-compact-restore/install.sh <mode> .
```

| モード | 使う場面 | 動く場所 | 設定の置き場所 | git の扱い |
|---|---|---|---|---|
| `plugin` | チームで使う（ローカルのセッション） | ローカルのみ | `.claude/settings.json`（プラグインの登録）/ `CLAUDE.md` | 登録設定をコミットして共有する（ノートは各自） |
| `team` | チームで使う。Claude Code Projects・クラウドセッションでも使う | ローカル・クラウド・Projects のスレッド | `.claude/settings.json` / `.claude/hooks/` / `.claude/commands/` / `CLAUDE.md` | 仕組みをコミットして共有する（ノートは各自） |
| `personal` | このプロジェクトで自分だけ使う | ローカルのみ | `.claude/settings.local.json` / `.claude/hooks/` / `.claude/commands/` / `CLAUDE.local.md` | `.git/info/exclude` で一切載せない |
| `global` | 自分の全プロジェクトで使う | ローカルのみ | `~/.claude/settings.json` / `~/.claude/hooks/` / `~/.claude/commands/` / `~/.claude/CLAUDE.md` | git のグローバル除外設定に追加する |

迷ったら、Claude Code Projects やクラウドで使うなら `team`、ローカルだけでチームに配るなら `plugin`、自分だけなら `personal` か `global` を選んでください。

`global` モードではプロジェクトの指定は不要です（`bash install.sh global`）。

- 何度実行しても設定は重複しません。既存の設定や CLAUDE.md のルールは残したままマージします
- 導入後は Claude Code を再起動してください。Desktop アプリの場合は新しいセッションを開きます
- `plugin` と `team` は切り替え式です。どちらかを実行すると、もう一方の設定は取り除かれます
- `team`・`plugin` と `global` を同じ人が併用すると注入が二重になるので、どちらか一方にしてください
- `plugin`・`personal`・`global` はローカルのセッションでのみ動きます。クラウドセッションは、リポジトリの settings.json で有効化したプラグインをインストールしないためです（[公式ドキュメント](https://code.claude.com/docs/ja/cloud-environments#what-carries-over-from-your-setup)）

### 取り除く

同じモードで末尾に `--uninstall` を付けて実行します。

```bash
bash ~/tools/claude-code-compact-restore/install.sh <mode> . --uninstall
```

- 作業ノートとスナップショット（`.claude/context/`）は残ります
- `.claude/context/` が残っている間は、その除外設定だけ残します（`global` を除く）。ユーザー指示の原文を含むファイルを誤ってコミットしないためです。除外設定も消すには、`.claude/context/` を削除してからもう一度 `--uninstall` を実行します
- `global` では除外設定も消えるので、各プロジェクトに残った `.claude/context/` が `git status` に出るようになります（実行時に注意が表示されます）
- 設定ファイルは導入前の状態に戻ります。キットの登録を外して空になった項目とフォルダだけを消し、もとから空だった項目やほかのファイルには触りません（例外として、`plugin` モードでもとから空だった `enabledPlugins` / `extraKnownMarketplaces` に登録した場合は、その項目ごと消えます。動作への影響はありません）

### キットを更新する

| モード | 更新のしかた |
|---|---|
| `team` | キットのクローンを `git pull` し、導入先で `install.sh team .` をもう一度実行してコミットします（スクリプトをリポジトリにコピーしているため） |
| `personal` / `global` | キットのクローンを `git pull` し、同じモードで `install.sh` をもう一度実行します |
| `plugin` / プラグインを直接入れた場合 | `claude plugin marketplace update mt-takao` で最新の版を取得し、`claude plugin update compact-restore@mt-takao` を実行して Claude Code を再起動します |

再実行しても設定は重複せず、既存の `.gitignore` や CLAUDE.md の並びも変わりません。

### 以前の版から移行する

v1・v2 から移行する場合も、使いたいモードで `install.sh` を実行するだけです。

- CLAUDE.md の「コンテキスト復元（圧縮対策）」の節は新しい運用ルールに置き換わり、v1 が `.gitignore` に書いた行は取り除かれます
- v1 でコミットしていた作業ノート・スナップショットは、git の追跡から外します（ファイルは手元に残ります。次のコミットで反映されます）
- Claude Code Projects で使う場合は、`plugin` ではなく `team` に切り替えてください（`install.sh team .` で `plugin` の設定は取り除かれます）

### チームで導入する場合

- **ローカルのセッションだけで使う**：導入担当者が `install.sh plugin .` を実行して PR にします。マージ後、各メンバーは pull して一度だけ `claude plugin install compact-restore@mt-takao --scope project` を実行します（リポジトリの設定は有効化だけで、ダウンロードはしないため）
- **Claude Code Projects・クラウドセッションでも使う**：`install.sh team .` でフックのスクリプトを直接コミットします。メンバーは pull するだけで使えます

どちらも python3 が必要です。

### プラグインとして直接入れる場合

リポジトリを書き換えずに自分の環境だけに入れることもできます（ローカルのセッション向け）。

```
/plugin marketplace add mt-takao/claude-code-compact-restore
/plugin install compact-restore@mt-takao
```

### Claude Desktop（Code タブ）で使う場合

Local セッションを開き、統合ターミナル（`` Ctrl+` ``）で上記コマンドを実行してください。フックの設定ファイルは CLI と共通です。

`/hooks` は Code タブでは使えないため、登録されたかどうかは Claude に「`.claude/settings.json` のフックを一覧にして」と聞いて確認してください。

Cowork タブではフックが発火しないという報告があります。

## Claude Code Projects で使う

[Claude Code Projects](https://code.claude.com/docs/ja/claude-projects) では、コーディネーター（プロジェクト会話）と各スレッド（クラウドセッション）のコンテキストは自動で管理され、手動の `/compact` は使いません。仕組みの効き方は次のとおりです。

| 対象 | フックは動くか | 文脈の残し方 |
|---|---|---|
| スレッド（リポジトリ 1 つのプロジェクト） | `team` で動く（`plugin` は動かない） | 自動圧縮の直前に退避し、直後に再注入する |
| スレッド（リポジトリ複数のプロジェクト） | 動かない（リポジトリの settings.json のフックもプラグインも読まれないため） | プロジェクトメモリとプロジェクト指示で残す |
| コーディネーター（プロジェクト会話） | 動かない | プロジェクトメモリとプロジェクト指示で残す |

設定は次の 3 つです。

1. **プロジェクトに追加するリポジトリに `install.sh team .` で導入してコミットする。** スレッドはクローンしたリポジトリの `.claude/settings.json` のフックを実行します。クラウドセッションはリポジトリで有効化したプラグインをインストールしないので、`plugin` モードは使えません
2. **[`templates/project-instructions.md`](templates/project-instructions.md) を「Project settings > Memory > プロジェクト指示」に貼る。** 決定事項はプロジェクトメモリに記憶する、途中経過はこまめに push する、完了報告に要点を含める、といったルールがコーディネーターと全スレッドに渡ります
3. **スレッドの区切りで `/checkpoint` を使う。** 作業ノートの更新に加えて、未コミットの変更を push し、後続のスレッドに必要な決定事項をプロジェクトメモリに記憶します

クラウドセッションの `.claude/context/` はその VM の中だけのもので、ほかのスレッドや作り直された VM には引き継がれません。そのためスレッド内では次のように役割を分けています。

- **同じスレッド内の自動圧縮**：スナップショットと作業ノートで復元する（これまでと同じ）
- **スレッドをまたぐ情報**：プロジェクトメモリに残す。セッション開始時のフックが、クラウドであることを検出してこの案内を自動で注入します
- **退避したスナップショット**：クラウドでは元のセッションの URL も記録するので、後からトランスクリプトをたどれます
- **キットを更新したとき**：`team` モードはスクリプトをリポジトリにコピーしているので、導入先で `install.sh team .` をもう一度実行してコミットします

## 使い方

- **普段**：設計の確定・タスクの完了・方針転換などの区切りで `checkpoint` コマンドを実行します
- **圧縮したいとき**：`/compact <focus>` を実行します。`checkpoint` コマンドが状況に合った focus を提案します（自動圧縮のみの環境では不要です）
- **圧縮後**：スナップショットと作業ノートが自動で注入されます。念のため「圧縮前にやっていたことと次にやることを教えて」と確認すると安心です

### 手動で復元する

自動の注入がうまく効かなかったときや、新しいセッションで続きをやるときは、次のように読み込ませます。

```
@.claude/context/latest-snapshot.md と @.claude/context/working-notes.md を読んで、
作業状態を3〜5行でまとめてください。確認するまで作業は再開しないでください。
```

もっと前の状態が必要なときは、`.claude/context/snapshots/` から該当日時のファイルを指定します（直近20件が残っています）。

## 調整

| 項目 | 場所 | 既定値 |
|---|---|---|
| 残すユーザー指示の数 | `plugins/compact-restore/scripts/pre_compact_snapshot.py` の `RECENT_USER_PROMPTS` | 8 |
| スナップショットの保持数 | 同 `KEEP` | 20 |
| 注入する最大文字数 | `plugins/compact-restore/scripts/post_compact_restore.py` の `SNAPSHOT_MAX` / `NOTES_MAX` | 12,000 / 6,000 |

## 注意事項

- **スナップショットにはユーザー指示の原文が残ります。** 会話に秘密情報を貼った場合は、`.claude/context/snapshots/` を確認・削除してください
- **会話記録の形式は Claude Code の内部仕様です。** 将来の変更で一部の情報が抜き出せなくなる可能性があります。その場合もフックはエラー終了せず（常に exit 0）、圧縮そのものは妨げません
- **Python コマンドの名前に注意してください。** Windows（WSL 以外）で `python3` が使えない場合は、設定ファイル内のコマンドを `python` または `py` に書き換えてください

## 変更履歴

主な変更は次のとおりです。詳しくは [CHANGELOG.md](CHANGELOG.md) を参照してください。

| 版 | 主な変更 |
|---|---|
| v1 | 作業ノート・圧縮前のスナップショット・圧縮後の再注入の 3 層構成（未公開） |
| v2 | 作業ノートを個人のものにし、`SessionStart` フックで注入。`team` / `personal` / `global` の 3 モードと `--uninstall` |
| v3.0 | プラグインとして配布（`plugin` モード）。Claude Code Projects・クラウドセッションに対応 |
| v3.0.1〜v3.0.5 | Projects のスレッドの発言・進捗表示、TaskCreate / TaskUpdate のタスクリストを記録。作業用の一時ファイルを除外 |
| インストーラの修正 | 再インストールで `.gitignore` と CLAUDE.md の並びを保つ。アンインストールで `.claude/context/` の除外を残し、もとの設定に戻す |

## 開発

```bash
bash tests/run_tests.sh
```

GitHub Actions で Ubuntu・macOS × Python 3.9・3.13 の組み合わせで実行しています。テストでは実際の Claude Code は起動しません。フックに渡される JSON と会話記録を模擬して、抽出処理・注入処理・クラウドセッションでの案内・プラグイン構成・4 モードのインストールとアンインストールを検証します。`claude` コマンドがあれば `claude plugin validate` も実行します。

このリポジトリ自体にも `team` モードで導入しています（`.claude/hooks/`・`.claude/commands/`・`.claude/settings.json`）。配布物ではなく、このリポジトリで作業するときの圧縮対策です。`plugins/compact-restore/` のスクリプトやコマンドを変えたら `bash install.sh team .` を再実行して同期してください。ずれているとテストが失敗します。

## 参考

- [Claude Code のコンテキスト・メモリ管理について解説した記事（koromo.io）](https://koromo.io/blog/claude-code-context-memory/) — 本ツールの着想元
- [Hooks reference - Claude Code Docs](https://code.claude.com/docs/en/hooks)
- [Claude Code Projects - Claude Code Docs](https://code.claude.com/docs/ja/claude-projects)
- [クラウド環境を設定する - Claude Code Docs](https://code.claude.com/docs/ja/cloud-environments)

## License

[MIT](LICENSE) © 2026 Takao Mukai
