# claude-code-compact-restore

[![test](https://github.com/mt-takao/claude-code-compact-restore/actions/workflows/test.yml/badge.svg)](https://github.com/mt-takao/claude-code-compact-restore/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[日本語](README.md) | English

A set of hooks and a slash command that keep your working context intact when Claude Code runs `/compact` or auto-compaction.
It works in local sessions, and via `team` mode in [Claude Code Projects](https://code.claude.com/docs/en/claude-projects) threads with one repository (cloud sessions that only auto-compact).

The latest version is v3.0.5. See the [changelog](#changelog) for what changed since v1.

## Why

Post-compaction summaries tend to lose concrete details such as which task was in progress, which files were touched, and why an approach was rejected. This tool fills that gap by combining two things:

- **Mechanical snapshots**: right before compaction, facts are extracted from the conversation transcript and git and saved
- **Structured notes**: Claude itself writes down intent and the reasoning behind decisions as working notes

## How it works

| Component | When it runs | What it does |
|---|---|---|
| `checkpoint` command | Manually, at natural breakpoints | Updates the working notes `.claude/context/working-notes.md` (goal, decisions, rejected options, current state, next step, open questions). `/compact-restore:checkpoint` when installed as a plugin, `/checkpoint` otherwise |
| `PreCompact` hook | Automatically, right before compaction | Saves a snapshot of the task list (TodoWrite or TaskCreate / TaskUpdate, or the progress checklist in Projects threads), recent user prompts, edited files (excluding scratch files in temp folders), updated memory files, git state and the last assistant message |
| `SessionStart` hook | Automatically, at session start and right after compaction | Injects the working notes. Right after compaction, it also injects the snapshot. In cloud sessions it also injects guidance on where to record things |

Working notes and snapshots are **personal**, so they are never committed to git in any install mode.

### Example snapshot

It is saved to `.claude/context/latest-snapshot.md` right before compaction and injected right after it (history lives in `.claude/context/snapshots/`).
Sections with nothing recorded (task list, memory, git, and so on) are omitted or shown as "none". The headings are written in Japanese; the translation below is for reference.

````markdown
# Pre-compaction snapshot (2026-10-12 21:04:13 / trigger: manual)

/compact focus: keep the decisions

## Task list in progress
- [x] Fix loading the config file
- [→] Add tests
- [ ] Update the README

## Recent user prompts (oldest → newest)
1. It crashes when the config file is missing, please fix it
2. Add tests too

## Files edited in this session (most recent last)
- src/config.py
- tests/test_config.py

## Git state
- Branch: `fix-config`
- Uncommitted changes:
```
 M src/config.py
?? tests/test_config.py
```

## Claude's last message before compaction (how far it got)
I made it fall back to defaults when the config file is missing. Next, I'll add tests.
````

- In cloud sessions, the URL of the original session follows the title
- In Projects threads, the "thread progress checklist" (✓ done / ✱ in progress / ○ not started) takes the place of the task list, and prompts are recorded as "sender: body"
- When memory files outside the project were updated, an "updated memory" section is added

## Installation

Requires Python 3.9 or later (standard library only). git is optional, but when present it enables recording git state and the ignore settings.

```bash
git clone https://github.com/mt-takao/claude-code-compact-restore.git ~/tools/claude-code-compact-restore
cd /path/to/your-project
bash ~/tools/claude-code-compact-restore/install.sh <mode> .
```

| Mode | Use case | Where it runs | Where settings go | git handling |
|---|---|---|---|---|
| `plugin` | The team uses it (local sessions) | Local only | `.claude/settings.json` (plugin registration) / `CLAUDE.md` | The registration is committed and shared (notes stay personal) |
| `team` | The team uses it, including in Claude Code Projects and cloud sessions | Local, cloud, and Projects threads | `.claude/settings.json` / `.claude/hooks/` / `.claude/commands/` / `CLAUDE.md` | The setup is committed and shared (notes stay personal) |
| `personal` | Only you, in this project | Local only | `.claude/settings.local.json` / `.claude/hooks/` / `.claude/commands/` / `CLAUDE.local.md` | Kept out of git entirely via `.git/info/exclude` |
| `global` | You, in all your projects | Local only | `~/.claude/settings.json` / `~/.claude/hooks/` / `~/.claude/commands/` / `~/.claude/CLAUDE.md` | Added to git's global ignore file |

If unsure: choose `team` for Claude Code Projects or the cloud, `plugin` to roll it out to a team that works locally, and `personal` or `global` for yourself only.

`global` mode does not take a project path (`bash install.sh global`).

- Running it repeatedly never duplicates settings. Existing settings and CLAUDE.md rules are kept and merged
- Restart Claude Code after installing. In the Desktop app, open a new session
- `plugin` and `team` are mutually exclusive. Running one removes the other's settings
- Using `team` or `plugin` together with `global` yourself injects everything twice, so pick one
- `plugin`, `personal` and `global` only work in local sessions. Cloud sessions don't install plugins that a repository's settings.json enables ([docs](https://code.claude.com/docs/en/cloud-environments#what-carries-over-from-your-setup))

### Uninstalling

Run the same mode with `--uninstall` appended.

```bash
bash ~/tools/claude-code-compact-restore/install.sh <mode> . --uninstall
```

- Working notes and snapshots (`.claude/context/`) are kept
- While `.claude/context/` still exists, its ignore entry is kept as well (except in `global` mode), so files containing your prompts verbatim aren't committed by accident. To remove that entry too, delete `.claude/context/` and run `--uninstall` again
- `global` removes the ignore entry too, so any `.claude/context/` left in your projects will show up in `git status` (a warning is printed)
- Settings files return to their state before installation. Only entries and folders emptied by removing the kit are deleted; entries that were already empty and other files are left alone (one exception: in `plugin` mode, if `enabledPlugins` / `extraKnownMarketplaces` was already empty before installing, the whole entry is removed; this has no effect on behavior)

### Updating the kit

| Mode | How to update |
|---|---|
| `team` | `git pull` your clone of the kit, run `install.sh team .` again in your repository, and commit (the scripts are copied into the repository) |
| `personal` / `global` | `git pull` your clone of the kit and run `install.sh` again in the same mode |
| `plugin` / plugin installed directly | Fetch the latest version with `claude plugin marketplace update mt-takao`, then run `claude plugin update compact-restore@mt-takao` and restart Claude Code |

Re-running never duplicates settings and keeps the order of your existing `.gitignore` and CLAUDE.md.

### Migrating from an earlier version

To migrate from v1 or v2, just run `install.sh` in the mode you want.

- The "コンテキスト復元（圧縮対策）" (context restore) section in CLAUDE.md is replaced with the current rules, and the lines v1 wrote to `.gitignore` are removed
- Working notes and snapshots committed under v1 are untracked from git (the files stay on disk; this takes effect with your next commit)
- For Claude Code Projects, switch from `plugin` to `team` (`install.sh team .` removes the `plugin` settings)

### Installing for a team

- **Local sessions only**: one person runs `install.sh plugin .` and opens a PR. Once merged, each member pulls and runs `claude plugin install compact-restore@mt-takao --scope project` once (the repository settings enable the plugin but don't download it)
- **Also in Claude Code Projects and cloud sessions**: run `install.sh team .` to commit the hook scripts directly. Members just pull

Both require python3.

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
| Threads (project with one repository) | Yes, with `team` (not `plugin`) | Snapshot right before auto-compaction, re-injected right after |
| Threads (project with several repositories) | No (neither a repository's settings.json hooks nor its plugins are loaded) | Project memory and project instructions |
| Coordinator (project conversation) | No | Project memory and project instructions |

Set it up in three steps:

1. **Run `install.sh team .` in a repository added to the project and commit it.** Threads run the hooks in the cloned repository's `.claude/settings.json`. Cloud sessions don't install plugins a repository enables, so `plugin` mode doesn't work there
2. **Paste [`templates/project-instructions.md`](templates/project-instructions.md) into "Project settings > Memory > Project instructions".** The coordinator and every thread then get rules such as: record decisions in project memory, push progress often, and include the key points in completion reports
3. **Run `/checkpoint` at a thread's breakpoints.** Besides updating the working notes, it pushes uncommitted changes and records decisions later threads need in project memory

In a cloud session, `.claude/context/` exists only inside that VM; other threads and recreated VMs don't see it. Within a thread, the roles are split as follows:

- **Auto-compaction within the same thread**: restored from the snapshot and working notes, as before
- **Information that crosses threads**: kept in project memory. The SessionStart hook detects the cloud environment and injects this guidance automatically
- **Saved snapshots**: in the cloud they also record the original session URL, so you can trace the transcript later
- **Updating the kit**: `team` mode copies the scripts into your repository, so run `install.sh team .` again in that repository and commit

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

## Changelog

The main changes are below. See [CHANGELOG.en.md](CHANGELOG.en.md) for details.

| Version | Main changes |
|---|---|
| v1 | Three layers: working notes, a pre-compaction snapshot, and re-injection after compaction (unreleased) |
| v2 | Working notes became personal and are injected by the `SessionStart` hook. Three modes, `team` / `personal` / `global`, plus `--uninstall` |
| v3.0 | Distributed as a plugin (`plugin` mode). Support for Claude Code Projects and cloud sessions |
| v3.0.1–v3.0.5 | Record Projects thread messages and progress checklists, and TaskCreate / TaskUpdate task lists. Leave scratch files out |
| Installer fixes | Re-installing keeps the order of `.gitignore` and CLAUDE.md. Uninstalling keeps the `.claude/context/` ignore entry and restores the original settings |

## Development

```bash
bash tests/run_tests.sh
```

GitHub Actions runs them on Ubuntu and macOS with Python 3.9 and 3.13. The tests don't launch the real Claude Code. They simulate the JSON passed to the hooks and the conversation transcript, and verify extraction, injection, the cloud-session guidance, the plugin layout, and install/uninstall for all four modes. When the `claude` command is available, they also run `claude plugin validate`.

## References

- [Article on Claude Code context and memory management (koromo.io, Japanese)](https://koromo.io/blog/claude-code-context-memory/) — the inspiration for this tool
- [Hooks reference - Claude Code Docs](https://code.claude.com/docs/en/hooks)
- [Claude Code Projects - Claude Code Docs](https://code.claude.com/docs/en/claude-projects)
- [Configure cloud environments - Claude Code Docs](https://code.claude.com/docs/en/cloud-environments)

## License

[MIT](LICENSE) © 2026 Takao Mukai
