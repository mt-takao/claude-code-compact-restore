# claude-code-compact-restore

[![test](https://github.com/mt-takao/claude-code-compact-restore/actions/workflows/test.yml/badge.svg)](https://github.com/mt-takao/claude-code-compact-restore/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[日本語](README.md) | English

A set of hooks and a slash command that keep your working context intact when Claude Code runs `/compact` or auto-compaction.

## Why

Post-compaction summaries tend to lose concrete details such as which task was in progress, which files were touched, and why an approach was rejected. This tool fills that gap by combining two things:

- **Mechanical snapshots**: right before compaction, facts are extracted from the conversation transcript and git and saved
- **Structured notes**: Claude itself writes down intent and the reasoning behind decisions as working notes

## How it works

| Component | When it runs | What it does |
|---|---|---|
| `/checkpoint` command | Manually, at natural breakpoints | Updates the working notes `.claude/context/working-notes.md` (goal, decisions, rejected options, current state, next step, open questions) |
| `PreCompact` hook | Automatically, right before compaction | Saves a snapshot of the task list (TodoWrite), recent user prompts, edited files, git state and the last assistant message |
| `SessionStart` hook | Automatically, at session start and right after compaction | Injects the working notes. Right after compaction, it also injects the snapshot |

Working notes and snapshots are **personal**, so they are never committed to git in any install mode.

## Installation

Requires Python 3.9 or later (standard library only). git is optional, but when present it enables recording git state and the ignore settings.

```bash
git clone https://github.com/mt-takao/claude-code-compact-restore.git ~/tools/claude-code-compact-restore
cd /path/to/your-project
bash ~/tools/claude-code-compact-restore/install.sh <mode> .
```

| Mode | Use case | Where settings go | git handling |
|---|---|---|---|
| `team` | The whole team uses it | `.claude/settings.json` / `CLAUDE.md` | The setup is committed and shared (notes stay personal) |
| `personal` | Only you, in this project | `.claude/settings.local.json` / `CLAUDE.local.md` | Kept out of git entirely via `.git/info/exclude` |
| `global` | You, in all your projects | `~/.claude/settings.json` / `~/.claude/CLAUDE.md` | Added to git's global ignore file |

`global` mode does not take a project path (`bash install.sh global`).

- Running it repeatedly never duplicates settings. Existing settings and CLAUDE.md rules are kept and merged
- Restart Claude Code after installing. In the Desktop app, open a new session
- Using both `team` and `global` yourself injects everything twice, so pick one
- To remove it, run the same mode with `--uninstall` appended. Working notes and snapshots are kept

### Installing for a team

1. One person runs `install.sh team .` and opens a PR with the changes
2. Once merged, members just pull to start using it (python3 is required)

### Using it in Claude Desktop (Code tab)

Open a Local session and run the commands above in the integrated terminal (`` Ctrl+` ``). The hook settings files are shared with the CLI.

`/hooks` is not available in the Code tab, so to confirm the hooks were registered, ask Claude to "list the hooks in `.claude/settings.json`".

There are reports that hooks do not fire in the Cowork tab.

## Usage

- **Day to day**: run `/checkpoint` at breakpoints such as finalizing a design, completing a task, or changing direction
- **When you want to compact**: run `/compact <focus>`. `/checkpoint` suggests a focus suited to the situation
- **After compaction**: the snapshot and working notes are injected automatically. For peace of mind, ask "What were you doing before compaction, and what's next?"

### Restoring manually

If automatic injection didn't take effect, or you're continuing in a new session, load them like this:

```
Read @.claude/context/latest-snapshot.md and @.claude/context/working-notes.md
and summarize the working state in 3–5 lines. Don't resume work until I confirm.
```

If you need an earlier state, point to the file for that date and time in `.claude/context/snapshots/` (the 20 most recent are kept).

## Configuration

| Setting | Location | Default |
|---|---|---|
| Number of user prompts kept | `RECENT_USER_PROMPTS` in `hooks/pre_compact_snapshot.py` | 8 |
| Number of snapshots kept | `KEEP` in the same file | 20 |
| Maximum characters injected | `SNAPSHOT_MAX` / `NOTES_MAX` in `hooks/post_compact_restore.py` | 12,000 / 6,000 |

## Caveats

- **Snapshots contain your prompts verbatim.** If you pasted secrets into the conversation, check and delete `.claude/context/snapshots/`
- **The transcript format is internal to Claude Code.** Future changes may prevent some information from being extracted. Even then, the hooks never exit with an error (always exit 0) and never block compaction itself
- **Watch the Python command name.** On Windows (outside WSL), if `python3` isn't available, change the command in the settings file to `python` or `py`

## Development

```bash
bash tests/run_tests.sh
```

The tests don't launch the real Claude Code. They simulate the JSON passed to the hooks and the conversation transcript, and verify extraction, injection, and install/uninstall for all three modes.

## References

- [Article on Claude Code context and memory management (koromo.io, Japanese)](https://koromo.io/blog/claude-code-context-memory/) — the inspiration for this tool
- [Hooks reference - Claude Code Docs](https://code.claude.com/docs/en/hooks)

## License

[MIT](LICENSE) © 2026 Takao Mukai
