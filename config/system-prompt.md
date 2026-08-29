# Yantra Enhanced Claude Session

Reference notes on what an "enhanced" Yantra session provides. **Not
auto-injected into Claude** - `yantra` launches Claude directly (optionally
Headroom-wrapped); this file documents the pieces that are delivered
through Claude Code's own native mechanisms instead, via `yantra install`.
See the README's [Hooks & Skills](../README.md#hooks--skills) section.

## What `yantra install` actually registers

### Safety hook (`hooks/safety_gates.js`)
A real Claude Code `PreToolUse` hook, registered in `~/.claude/settings.json`.
Blocks before execution, for every Claude Code session on the machine:
- `rm -rf` / `Remove-Item -Recurse` (file deletion)
- `git reset --hard` (discard work)
- `git rebase -i` (interactive rebase)
- `DELETE FROM` / `DROP TABLE` / `truncate table` (database operations)
- `git push --force` (force push)

### `context-analysis` skill (`skills/context-analysis/SKILL.md`)
A real Claude Code skill, installed to `~/.claude/skills/`. Summarizes git
branch, status, and uncommitted changes - on demand (`/context-analysis`,
or auto-loaded when relevant), not injected into every request.

## What `yantra` (the launcher itself) does

- Launches Claude, wrapped with [Headroom](https://github.com/headroomlabs-ai/headroom)
  for token optimization if it's installed and enabled
- Gathers git/system context for **your own terminal display** at startup -
  this is not sent to Claude
- Neither of the above requires `yantra install` - they're independent
