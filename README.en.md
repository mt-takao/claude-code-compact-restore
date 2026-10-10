# claude-code-compact-restore

[![test](https://github.com/mt-takao/claude-code-compact-restore/actions/workflows/test.yml/badge.svg)](https://github.com/mt-takao/claude-code-compact-restore/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[日本語](README.md) | English

A set of hooks and a slash command that keep your working context intact when Claude Code runs `/compact` or auto-compaction.
It works in local sessions and in [Claude Code Projects](https://code.claude.com/docs/en/claude-projects) threads (cloud sessions that only auto-compact).

## Why

Post-compaction summaries tend to lose concrete details such as which task was in progress, which files were touched, and why an approach was rejected. This tool fills that gap by combining two things:

- **Mechanical snapshots**: right before compaction, facts are extracted from the conversation transcript and git and saved
- **Structured notes**: Claude itself writes down intent and the reasoning behind decisions as working notes

## How it works

| Component | When it runs | What it does |
|---|---|---|
| `checkpoint` command | Manually, at natural breakpoints | Updates the working notes `.claude/context/working-notes.md` (goal, decisions, rejected options, current state, next step, open questions). `/compact-restore:checkpoint` when installed as a plugin, `/checkpoint` otherwise |
| `PreCompact` hook | Automatically, right before compaction | Saves a snapshot of the task list (TodoWrite), recent user prompts, edited files, git state and the last assistant message |
| `SessionStart` hook | Automatically, at session start and right after compaction | Injects the working notes. Right after compaction, it also injects the snapshot. In cloud sessions it also injects guidance on where to record things |

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
| `plugin` (recommended) | The team uses it, including in Claude Code Projects and cloud sessions | `.claude/settings.json` (plugin registration) / `CLAUDE.md` | The registration is committed and shared (notes stay personal) |
| `team` | The whole team uses it | `.claude/settings.json` / `CLAUDE.md` | The setup is committed and shared (notes stay personal) |
| `personal` | Only you, in this project | `.claude/settings.local.json` / `CLAUDE.local.md` | Kept out of git entirely via `.git/info/exclude` |
| `global` | You, in all your projects | `~/.claude/settings.json` / `~/.claude/CLAUDE.md` | Added to git's global ignore file |

`global` mode does not take a project path (`bash install.sh global`).

- Running it repeatedly never duplicates settings. Existing settings and CLAUDE.md rules are kept and merged
- Restart Claude Code after installing. In the Desktop app, open a new session
- `plugin` and `team` are mutually exclusive. Running one removes the other's settings
- Using `team` or `plugin` together with `global` yourself injects everything twice, so pick one
- `personal` and `global` only work in local sessions; they don't carry over to cloud sessions
- To remove it, run the same mode with `--uninstall` appended. Working notes and snapshots are kept

### Installing for a team

1. One person runs `install.sh plugin .` and opens a PR with the changes
2. Once merged, members pull, open Claude Code and accept the folder trust prompt; the plugin installs automatically (python3 is required)

To commit the hook scripts directly instead of using the plugin, use `install.sh team .`.

### Installing the plugin for yourself only

You can also install it into your own environment without changing the repository (for local sessions):

```
/plugin marketplace add mt-takao/claude-code-compact-restore
/plugin install compact-restore@mt-takao
```

### Using it in Claude Desktop (Code tab)

Open a Local session and run the commands above in the integrated terminal (`` Ctrl+` ``). The hook settings files are shared with the CLI.

`/hooks` is not available in the Code tab, so to confirm the hooks were registered, ask Claude to "list the hooks in `.claude/settings.json`".

There are reports that hooks do not fire in the Cowork tab.

## Using it with Claude Code Projects

In [Claude Code Projects](https://code.claude.com/docs/en/claude-projects), the context of the coordinator (the project conversation) and of each thread (a cloud session) is managed automatically, and you don't run `/compact` yourself. Here is where the kit takes effect:

| Target | Do the hooks run? | How context is kept |
|---|---|---|
| Threads (project with one repository) | Yes, with `plugin` or `team` | Snapshot right before auto-compaction, re-injected right after |
| Threads (project with several repositories) | Only with `plugin` (hooks in a repository's settings.json aren't applied) | Same as above |
| Coordinator (project conversation) | No | Project memory and project instructions |

Set it up in three steps:

1. **Run `install.sh plugin .` in a repository added to the project and commit it.** Threads install the plugin from the cloned repository's settings. With several repositories, one of them is enough for every thread
2. **Paste [`templates/project-instructions.md`](templates/project-instructions.md) into "Project settings > Memory > Project instructions".** The coordinator and every thread then get rules such as: record decisions in project memory, push progress often, and include the key points in completion reports
3. **Run `/compact-restore:checkpoint` at a thread's breakpoints.** Besides updating the working notes, it pushes uncommitted changes and records decisions later threads need in project memory

In a cloud session, `.claude/context/` exists only inside that VM; other threads and recreated VMs don't see it. Within a thread, the roles are split as follows:

- **Auto-compaction within the same thread**: restored from the snapshot and working notes, as before
- **Information that crosses threads**: kept in project memory. The SessionStart hook detects the cloud environment and injects this guidance automatically
- **Saved snapshots**: in the cloud they also record the original session URL, so you can trace the transcript later

## Usage

- **Day to day**: run the `checkpoint` command at breakpoints such as finalizing a design, completing a task, or changing direction
- **When you want to compact**: run `/compact <focus>`. The `checkpoint` command suggests a focus suited to the situation (not needed where only auto-compaction runs)
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
| Number of user prompts kept | `RECENT_USER_PROMPTS` in `plugins/compact-restore/scripts/pre_compact_snapshot.py` | 8 |
| Number of snapshots kept | `KEEP` in the same file | 20 |
| Maximum characters injected | `SNAPSHOT_MAX` / `NOTES_MAX` in `plugins/compact-restore/scripts/post_compact_restore.py` | 12,000 / 6,000 |

## Caveats

- **Snapshots contain your prompts verbatim.** If you pasted secrets into the conversation, check and delete `.claude/context/snapshots/`
- **The transcript format is internal to Claude Code.** Future changes may prevent some information from being extracted. Even then, the hooks never exit with an error (always exit 0) and never block compaction itself
- **Watch the Python command name.** On Windows (outside WSL), if `python3` isn't available, change the command in the settings file to `python` or `py`

## Development

```bash
bash tests/run_tests.sh
```

The tests don't launch the real Claude Code. They simulate the JSON passed to the hooks and the conversation transcript, and verify extraction, injection, the cloud-session guidance, the plugin layout, and install/uninstall for all four modes. When the `claude` command is available, they also run `claude plugin validate`.

## References

- [Article on Claude Code context and memory management (koromo.io, Japanese)](https://koromo.io/blog/claude-code-context-memory/) — the inspiration for this tool
- [Hooks reference - Claude Code Docs](https://code.claude.com/docs/en/hooks)
- [Claude Code Projects - Claude Code Docs](https://code.claude.com/docs/en/claude-projects)
- [Configure cloud environments - Claude Code Docs](https://code.claude.com/docs/en/cloud-environments)

## License

[MIT](LICENSE) © 2026 Takao Mukai
