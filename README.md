# claude-code-compact-restore

[![test](https://github.com/mt-takao/claude-code-compact-restore/actions/workflows/test.yml/badge.svg)](https://github.com/mt-takao/claude-code-compact-restore/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Claude Code で `/compact` や自動圧縮（auto-compact）が走っても、作業の文脈を失わないためのフックとコマンドのセットです。

> **English summary:** Hooks and a slash command that preserve working context across Claude Code compaction. A `PreCompact` hook snapshots your task list, recent prompts, edited files and git state; a `SessionStart` hook re-injects that snapshot plus your personal working notes after compaction. Install per team, per project, or globally with `bash install.sh team|personal|global`. Requires Python 3.9+.

## なぜ必要か

圧縮後の要約では、「どのタスクが途中か」「どのファイルを触ったか」「なぜその案を却下したか」といった具体的な情報が抜け落ちがちです。このツールは、次の2つを組み合わせて圧縮後の文脈を補います。

- **機械的な退避**：圧縮の直前に、会話記録と git から事実を抜き出して保存する
- **構造化ノート**：Claude 自身に、意図や判断の理由をノートとして書かせておく

## 仕組み

| 部品 | いつ動くか | 何をするか |
|---|---|---|
| `/checkpoint` コマンド | 作業の区切りで手動実行 | 作業ノート `.claude/context/working-notes.md` を更新する（ゴール・決定事項・却下案・現在地・次の一手・未解決の論点） |
| `PreCompact` フック | 圧縮の直前に自動 | タスクリスト（TodoWrite）・直近のユーザー指示・編集ファイル・git 状態・直前の発言をスナップショットとして退避する |
| `SessionStart` フック | セッション開始時と圧縮直後に自動 | 作業ノートを注入する。圧縮直後はスナップショットもあわせて注入する |

作業ノートとスナップショットは**個人のもの**なので、どの導入モードでも git にはコミットされません。

## 導入

要件は Python 3.9 以上（標準ライブラリのみ）です。git はなくても動きますが、あると git 状態の記録と除外設定が有効になります。

```bash
git clone https://github.com/mt-takao/claude-code-compact-restore.git ~/tools/claude-code-compact-restore
cd /path/to/your-project
bash ~/tools/claude-code-compact-restore/install.sh <mode> .
```

| モード | 使う場面 | 設定の置き場所 | git の扱い |
|---|---|---|---|
| `team` | チーム全員で使う | `.claude/settings.json` / `CLAUDE.md` | 仕組みをコミットして共有する（ノートは各自） |
| `personal` | このプロジェクトで自分だけ使う | `.claude/settings.local.json` / `CLAUDE.local.md` | `.git/info/exclude` で一切載せない |
| `global` | 自分の全プロジェクトで使う | `~/.claude/settings.json` / `~/.claude/CLAUDE.md` | git のグローバル除外設定に追加する |

`global` モードではプロジェクトの指定は不要です（`bash install.sh global`）。

- 何度実行しても設定は重複しません。既存の設定や CLAUDE.md のルールは残したままマージします
- 導入後は Claude Code を再起動してください。Desktop アプリの場合は新しいセッションを開きます
- `team` と `global` を同じ人が併用すると注入が二重になるので、どちらか一方にしてください
- 取り除くときは、同じモードで末尾に `--uninstall` を付けて実行します。作業ノートとスナップショットは残ります

### チームで導入する場合

1. 導入担当者が `install.sh team .` を実行し、変更を PR にする
2. マージ後、メンバーは pull するだけで使えます（python3 が必要です）

### Claude Desktop（Code タブ）で使う場合

Local セッションを開き、統合ターミナル（`` Ctrl+` ``）で上記コマンドを実行してください。フックの設定ファイルは CLI と共通です。

`/hooks` は Code タブでは使えないため、登録されたかどうかは Claude に「`.claude/settings.json` のフックを一覧にして」と聞いて確認してください。

Cowork タブではフックが発火しないという報告があります。

## 使い方

- **普段**：設計の確定・タスクの完了・方針転換などの区切りで `/checkpoint` を実行します
- **圧縮したいとき**：`/compact <focus>` を実行します。`/checkpoint` が状況に合った focus を提案します
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
| 残すユーザー指示の数 | `hooks/pre_compact_snapshot.py` の `RECENT_USER_PROMPTS` | 8 |
| スナップショットの保持数 | 同 `KEEP` | 20 |
| 注入する最大文字数 | `hooks/post_compact_restore.py` の `SNAPSHOT_MAX` / `NOTES_MAX` | 12,000 / 6,000 |

## 注意事項

- **スナップショットにはユーザー指示の原文が残ります。** 会話に秘密情報を貼った場合は、`.claude/context/snapshots/` を確認・削除してください
- **会話記録の形式は Claude Code の内部仕様です。** 将来の変更で一部の情報が抜き出せなくなる可能性があります。その場合もフックはエラー終了せず（常に exit 0）、圧縮そのものは妨げません
- **Python コマンドの名前に注意してください。** Windows（WSL 以外）で `python3` が使えない場合は、設定ファイル内のコマンドを `python` または `py` に書き換えてください

## 開発

```bash
bash tests/run_tests.sh
```

テストでは実際の Claude Code は起動しません。フックに渡される JSON と会話記録を模擬して、抽出処理・注入処理・3モードのインストールとアンインストールを検証します。

## 参考

- [Claude Code のコンテキスト・メモリ管理について解説した記事（koromo.io）](https://koromo.io/blog/claude-code-context-memory/) — 本ツールの着想元
- [Hooks reference - Claude Code Docs](https://code.claude.com/docs/en/hooks)

## License

[MIT](LICENSE) © 2026 Takao Mukai
