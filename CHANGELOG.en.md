# Changelog

[日本語](CHANGELOG.md) | English

The plugin version is the `version` in [`plugin.json`](plugins/compact-restore/.claude-plugin/plugin.json).
Fixes that touch only the installer don't bump it and are listed as "Installer".
The design history and real-world verification results are in [docs/development-log.md](docs/development-log.md) (Japanese).

## Installer (2026-10-13, PR #10 and #11)

- After uninstalling, the ignore entry for `.claude/context/` (working notes and snapshots) is kept while that folder still exists, so files containing your prompts verbatim don't show up in `git status` and get committed by accident (`team` / `plugin` / `personal`). Delete the folder and run `--uninstall` again to remove the entry too
- Uninstalling `global` removes the ignore entry and warns that any `.claude/context/` left in your projects will now show up in `git status`
- Uninstalling no longer removes `hooks` / `enabledPlugins` / `extraKnownMarketplaces` entries that were already empty before; only entries emptied by removing the kit's own registration are removed
- Uninstalling removes `hooks` / `commands` folders it leaves empty (folders with other files are kept)

## v3.0.5 (2026-10-12)

- When a Projects thread's progress checklist is recorded, the empty "task list" section is no longer shown

## v3.0.4 (2026-10-12)

- Task lists created with TaskCreate / TaskUpdate are now recorded in snapshots. Creates and updates are replayed in order, and deleted tasks are dropped
- The empty-state text changed from "no TodoWrite record" to "no task list record"

## v3.0.3 (2026-10-12)

- The latest progress checklist of a Projects thread is recorded in snapshots as "thread progress checklist"

## Installer (2026-10-12, PR #4 and #5)

- Re-installing keeps the `.gitignore` block and the CLAUDE.md guidance section in place (they used to move to the end and could swap order with sections added after them)

## v3.0.2 (2026-10-12)

- Scratch files in temp folders and the scratchpad are no longer listed as edited files
- Memory files outside the project are listed under their own "updated memory" heading

## v3.0.1 (2026-10-11)

- In Projects threads, human messages arrive wrapped in notification data, so snapshots now record only the message body and its sender ("sender: body"). Notifications from other sessions and workers are not recorded
- "Last assistant message" now uses the reply the user actually saw (the body passed to the reply tool)

## v3.0.0 (2026-10-11)

- **Plugin distribution**: install it as the `compact-restore` plugin from the `mt-takao` marketplace. The installer gains a `plugin` mode (for local sessions). `plugin` and `team` are mutually exclusive and never register twice
- **Claude Code Projects and cloud sessions**: the `SessionStart` hook detects cloud sessions and Projects threads and injects guidance to push often and to record cross-thread decisions in project memory
- Snapshots taken in cloud sessions record the original session URL
- In the cloud, the `checkpoint` command also pushes uncommitted changes and updates project memory
- Added the project instructions template [`templates/project-instructions.md`](templates/project-instructions.md)
- Use `team` mode for Projects: cloud sessions don't install plugins a repository enables, and threads in projects with several repositories don't load repository hooks

## v2 (2026-09-26, first public release)

- Working notes became personal (v1 assumed they were committed and shared with the team)
- Working notes are injected by the `SessionStart` hook instead of a CLAUDE.md `@import`, so `global` installs can read each project's notes
- The installer gained three modes, `team` / `personal` / `global`, plus `--uninstall` and migration from v1 (committed notes are untracked from git)
- MIT license, GitHub Actions (Ubuntu and macOS × Python 3.9 and 3.13), automated tests, and Japanese and English READMEs

## v1 (unreleased)

- Built as three layers: working notes, a `PreCompact` snapshot hook, and re-injection right after compaction
