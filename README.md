# 🛟 Yantra - Enhanced Claude Sessions

[![Tests](https://github.com/gutti-raviteja4/yantra-v1/actions/workflows/tests.yml/badge.svg)](https://github.com/gutti-raviteja4/yantra-v1/actions/workflows/tests.yml)

**Launches Claude CLI with token optimization ([Headroom](https://github.com/headroomlabs-ai/headroom)), plus an optional safety hook and context-analysis skill registered directly with Claude Code.**

**Version:** 0.1.0 | **Python:** 3.11+ | **License:** MIT

📖 **[ARCHITECTURE.md](ARCHITECTURE.md)** - the "why" behind every
non-obvious decision here (config resolution, the Windows-specific fixes,
the `--no-mcp` default, native hooks/skills instead of a subprocess
wrapper), plus an FAQ for questions like "is this safe" and "how do I know
the numbers aren't cherry-picked."

---

## Status & Limitations

Read this before relying on it - stated plainly rather than left for you to discover:

- **Tested on Windows.** macOS/Linux code paths exist (the `yantra` shell
  stub, POSIX path handling throughout) and pass CI's unit tests on both,
  but haven't been exercised end-to-end (a real `yantra` launch) on real
  Mac/Linux hardware yet. If you hit something there, please open an issue.
- **The evidence behind the token-optimization numbers is a handful of
  real, measured test runs** (documented below with exact figures) - not a
  benchmark suite. Results ranged from *worse* (trivial prompts, nothing to
  compress) to *44% cheaper* on one realistic content-heavy task tested so
  far. Your mileage will vary by workload - see
  [Configuration](#configuration) for the actual numbers and why.
- **The safety hook is pattern-matching, not a security boundary.** It
  catches the obvious destructive commands (`rm -rf`, `git reset --hard`,
  etc.) as a convenience. It's straightforward to write a destructive
  command that doesn't match its patterns - don't rely on it as your only
  safety net.
- **Automated tests exist** (`tests/`, run via CI on Windows/Linux/macOS)
  for the pure logic - config loading, launch-command resolution, the hook
  merge/idempotency logic, and the real `safety_gates.js` hook script.
  They don't cover a live end-to-end `yantra` launch against real Claude/
  Headroom - that's still manually verified.

## Quick Start

### One-Time Setup (per machine)

Two independent, optional steps - run either, both, or neither:

```bash
python yantra.py setup      # Install Headroom (token optimization)
python yantra.py install    # Register safety hook + skill with Claude Code (global)
```

`setup` installs [Headroom](https://github.com/headroomlabs-ai/headroom),
which wraps Claude sessions to cut token consumption - everything else in
Yantra needs zero external dependencies. `install` shows an exact preview
and asks for confirmation before registering anything - see
[Hooks & Skills](#hooks--skills).

### Launch Enhanced Claude Session

```bash
# Simple command, from any directory (after PATH setup - see below)
yantra

# Or directly - identical behavior
python yantra.py

# Skip or force Headroom for just this run, without touching config
yantra --no-headroom
yantra --headroom
```

That's it! Yantra will:
1. ✅ Check if you're logged into Claude
2. 🔐 Open login page in browser if needed
3. 🧠 Wrap the session with Headroom for token optimization (if installed)
4. 🚀 Launch interactive Claude

> Skipped `setup`, or Headroom isn't installed? Yantra still launches Claude
> normally - just without token optimization - and prints a reminder.
> Skipped `install`? Claude launches without the safety hook or skill; run
> it any time, it doesn't need to happen before your first launch.

### Enabling the bare `yantra` command

`yantra.bat` (Windows) / `yantra` (macOS/Linux) are included so you can just
type `yantra` from any directory. Add the project folder to your PATH once:

```powershell
# Windows (PowerShell) - persists for new terminals
[Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path","User") + ";$PWD", "User")
```

```bash
# macOS/Linux - add to ~/.bashrc or ~/.zshrc
echo 'export PATH="$PATH:'"$(pwd)"'"' >> ~/.bashrc && source ~/.bashrc
```

---

## Features

✅ **Token Optimization** (optional - `yantra setup`)
- Wraps sessions with [Headroom](https://github.com/headroomlabs-ai/headroom)
- Compresses context before it reaches Claude, cutting token usage
- Falls back to a normal launch automatically if not installed

✅ **Safety Gates** (optional, global - `yantra install`)
- Blocks dangerous operations (rm -rf, git reset --hard, DELETE FROM, etc.)
- Registered as a real Claude Code `PreToolUse` hook, not a Yantra wrapper -
  applies to every Claude Code session on the machine, not just `yantra`

✅ **Context Analysis Skill** (optional, global - `yantra install`)
- A real Claude Code [Skill](https://code.claude.com/docs/en/skills):
  `/context-analysis`, or auto-loaded when relevant
- Summarizes git branch/status on demand - costs nothing unless used
  (unlike a hook that runs on every tool call)

✅ **Cross-Platform**
- Windows, macOS, Linux
- No external dependencies (Headroom is the one optional exception)

> Yantra deliberately doesn't reinvent context injection, safety gates, or
> custom instructions by wrapping Claude in a subprocess - Claude Code
> already has real, better mechanisms for all three (hooks, skills,
> `CLAUDE.md`). `yantra install` registers Yantra's two pieces with those
> real mechanisms instead. See [Hooks & Skills](#hooks--skills) below.

---

## Architecture

```
Yantra v1 Session Flow:
┌──────────────────────────────────┐
│ yantra                           │
└────────────┬─────────────────────┘
             ↓
┌──────────────────────────────────┐
│ 1. Load Configuration            │
│    (config/, skills, hooks)      │
└────────────┬─────────────────────┘
             ↓
┌──────────────────────────────────┐
│ 2. Validate Environment          │
│    (Node.js, Claude CLI,         │
│     Headroom)                    │
└────────────┬─────────────────────┘
             ↓
┌──────────────────────────────────┐
│ 3. Inject Context                │
│    (git, system, filesystem -    │
│     shown to you, not to Claude) │
└────────────┬─────────────────────┘
             ↓
┌──────────────────────────────────┐
│ 4. Launch Claude                 │
│    (wrapped with Headroom if     │
│     available and enabled)       │
└──────────────────────────────────┘

Separately, one-time and global:
┌──────────────────────────────────┐
│ yantra install                   │
└────────────┬─────────────────────┘
             ↓
   Registers safety hook + skill directly
   with Claude Code's own config
   (~/.claude/settings.json, ~/.claude/skills/)
   - applies to every session, everywhere
```

---

## How It Works

### Launch Command

```bash
# Launch Yantra enhanced session (works in all shells)
yantra

# Verbose mode (shows initialization steps)
yantra -v

# One-time: install Headroom for token optimization
yantra setup

# One-time: register safety hook + skill with Claude Code (global)
yantra install
yantra uninstall     # remove exactly what install added

# Get help
yantra -h
```

`yantra` is a thin OS-native stub (`yantra.bat` on Windows, `yantra` on
macOS/Linux) that forwards straight to `python yantra.py` - all the actual
logic lives in that one Python file, so behavior is identical on every OS.
No bare command set up yet? `python yantra.py` works the same way.

### Startup Flow

When you run `yantra` (equivalently, `python yantra.py`), here's what happens:

```
yantra.py (entry point)
    ↓
1. Create SessionLauncher instance
   ├─ Creates ConfigLoader
   ├─ Creates EnvironmentValidator
   ├─ Creates ContextInjector
   └─ Creates HookManager
    ↓
2. Call SessionLauncher.initialize()
   ├─ ConfigLoader.load()                    → Reads config/yantra.config.json
   ├─ ConfigLoader.substitute_environment()  → Replaces ${VAR} with env values
   ├─ EnvironmentValidator.validate_all()    → Checks Node.js, Claude CLI
   ├─ ContextInjector.inject_context()       → Gathers git, system, filesystem info
   ├─ HookManager.load_hooks()               → Loads hooks/safety_gates.js etc.
   └─ HookManager.validate_hooks()           → Validates hook configuration
    ↓
3. Call SessionLauncher.start_interactive_session()
   ├─ is_authenticated()                     → Check if logged into Claude
   ├─ authenticate()                         → Open browser for login (if needed)
   ├─ _build_claude_environment()            → Builds env dict (no credentials)
   ├─ print_session_info()                   → Show context gathered (to you, not Claude)
   └─ _build_launch_command()                → ["claude"], or Headroom-wrapped if available
            ↓
       🎉 Claude launches - Headroom-wrapped if installed and enabled
```

`HookManager.load_hooks()`/`validate_hooks()` load `hooks.json` for the
console summary and validation above - they don't register anything with
Claude Code. That's a separate, explicit step: see
[Hooks & Skills](#hooks--skills) and `yantra install`.

### Module Responsibilities

| Module | File | Purpose |
|--------|------|---------|
| **SessionLauncher** | `launcher/session.py` | Orchestrates all components, builds the launch command |
| **ConfigLoader** | `launcher/config.py` | Loads configuration files, substitutes environment variables |
| **EnvironmentValidator** | `launcher/validator.py` | Validates Node.js, Claude CLI, Headroom |
| **ContextInjector** | `launcher/context.py` | Gathers git branch, system info, working directory (for display) |
| **HookManager** | `launcher/hooks.py` | Loads `hooks.json` for console summary/validation |
| **claude_extras** | `launcher/claude_extras.py` | `yantra install`/`uninstall` - registers the safety hook + skill with Claude Code itself |

### Initialization Checklist

When `SessionLauncher.initialize()` runs, here's what happens:

- ✅ Config files loaded from `config/` directory
- ✅ Environment variables substituted (${VAR} → actual value)
- ✅ Node.js 20+ verified
- ✅ Claude CLI found and working
- ✅ Machine context gathered (git, system, filesystem) - for display, not delivered to Claude
- ✅ `hooks.json` loaded and validated for the console summary
- ✅ Ready to launch Claude

---

## Project Structure

```
yantra-v1/
├── yantra.py                  # Main CLI entry point (all logic lives here)
├── yantra.bat                 # Windows stub - forwards to yantra.py
├── yantra                     # macOS/Linux stub - forwards to yantra.py
├── launcher/                  # Core modules
│   ├── __init__.py
│   ├── session.py            # Session orchestrator
│   ├── config.py             # Configuration loader
│   ├── validator.py          # Environment validation
│   ├── context.py            # Context injection (shown to you, not Claude)
│   ├── hooks.py              # hooks.json loader (console summary/validation)
│   └── claude_extras.py      # `yantra install`/`uninstall` - registers the
│                              #   hook + skill with Claude Code itself
├── config/                    # Configuration files
│   ├── yantra.config.json    # Main config (skills, hooks, headroom)
│   ├── hooks.json            # Safety-gate rules (documentation)
│   └── system-prompt.md      # Reference notes (not auto-injected)
├── hooks/                     # Hook implementations
│   └── safety_gates.js       # Real Claude Code PreToolUse hook -
│                              #   registered globally by `yantra install`
├── skills/                    # Skill source templates
│   └── context-analysis/
│       └── SKILL.md          # Installed to ~/.claude/skills/ by `yantra install`
├── tests/                     # unittest suite - see Testing section below
├── .github/workflows/         # CI - runs tests/ on every push (Win/Linux/macOS)
├── requirements.txt           # Python dependencies (none!)
├── .env.example               # Environment variable template (no required vars)
├── .gitignore                 # Git ignore rules
├── LICENSE                    # MIT license
├── README.md                  # This file
└── ARCHITECTURE.md            # Design decisions, the "why", FAQ
```

---

## Usage

### Launch Yantra Session

```bash
yantra
```

Yantra will automatically:
1. Check if you're logged into Claude
2. Open login page if authentication needed
3. Load configuration
4. Gather machine context (git branch, working directory, system info) for display
5. Wrap the session with Headroom for token optimization (if installed)
6. Launch interactive Claude terminal

The safety hook and context-analysis skill apply if you've separately run
`yantra install` - see [Hooks & Skills](#hooks--skills).

### Verbose Mode

```bash
yantra -v
```

Shows detailed initialization steps and session information.

---

## Configuration

### yantra.config.json

```json
{
  "skills": {
    "context_analysis": {
      "name": "Context Analysis",
      "description": "Analyze project context (git, files, system)",
      "enabled": true
    }
  },
  "environment": {
    "YANTRA_VERSION": "0.1.0"
  },
  "headroom": {
    "enabled": true,
    "args": ["--no-mcp"]
  }
}
```

The `skills` block here is descriptive metadata only (shown in
`print_session_info()`), not the mechanism that installs a skill - that's
`yantra install`, which reads from `skills/context-analysis/SKILL.md`
directly. See [Hooks & Skills](#hooks--skills).

`headroom.enabled` toggles the Headroom wrap on/off; `headroom.args` are extra
flags forwarded to `headroom wrap claude` (e.g. `["--memory"]`, `["--1m"]` -
see `headroom wrap claude --help` for the full list).

#### Why `--no-mcp` is the default

Measured with `claude -p "..." --output-format json` (real billed usage, not
an estimate) on a trivial prompt with nothing to compress:

| | Cost | Input tokens | Cache creation |
|---|---:|---:|---:|
| Plain `claude` | $0.0253 | 2 | 5,158 |
| `headroom wrap claude` (no flags) | $0.0527 | 2,814 | 10,954 |
| `headroom wrap claude --no-mcp` | $0.0222 | 2,814 | 2,956 |

Headroom auto-registers its own MCP tools (`headroom_compress`,
`headroom_retrieve`, `headroom_stats`) by default - their schemas get billed
as input/cache tokens on *every* request, whether or not you use them.
`--no-mcp` removes that, landing below the unwrapped baseline. A separate,
smaller fixed cost remains regardless of `--no-mcp` (Headroom's own
`--tool-search` docs name it: routing through a custom proxy URL disrupts
Claude Code's normal tool-schema cache lineage - issue #746 upstream).

**This means Headroom's savings only show up on content worth compressing**
(large tool output, JSON, long file reads - see Headroom's own claimed
15-20% savings for coding agents) **over a real session** - not on a single
trivial prompt, which only pays the fixed tax and never sees a discount.
Judge it on a realistic session (`headroom stats` / `headroom dashboard`
after real work), not a one-off "what time is it" test.

Want Headroom's memory/retrieve MCP tools back despite the cost? Set
`"args": []` in your config.

#### Toggling Headroom

Two ways, for two different needs:

| Method | Scope | Use it when... |
|---|---|---|
| `headroom.enabled` in `yantra.config.json` | Persistent, every launch | You want it on/off by default going forward |
| `yantra --no-headroom` / `yantra --headroom` | This run only | You want to override the config just once, without editing it |

```bash
yantra --no-headroom    # skip Headroom for this session, even if config enables it
yantra --headroom       # force Headroom on for this session, even if config disables it
yantra -v --no-headroom # combine with other flags normally
```

### hooks.json

Documents the safety-gate rules (the actual blocked patterns live in
`hooks/safety_gates.js`, which `yantra install` registers with Claude Code -
see [Hooks & Skills](#hooks--skills)):

```json
{
  "hooks": [
    {
      "id": "safety_gates",
      "type": "PreToolUse",
      "enabled": true,
      "description": "Block destructive operations"
    }
  ]
}
```

### system-prompt.md

Reference material for what an enhanced session should know about (git
context, safety gates). Not injected into Claude automatically - see
[Hooks & Skills](#hooks--skills) for how Yantra actually delivers
equivalents to Claude, and `CLAUDE.md` for project-level instructions if
you want more.

---

## Hooks & Skills

Claude Code already has real, native mechanisms for safety rules and
on-demand context - hooks (`~/.claude/settings.json`) and skills
(`~/.claude/skills/`) - that are more capable than anything Yantra could
deliver by wrapping Claude in a subprocess. So Yantra doesn't try to inject
a custom system prompt or gather context for you to hand to Claude; instead,
`yantra install` registers two pieces directly with Claude Code itself:

```bash
yantra install      # preview the exact change, then confirm
yantra uninstall     # remove exactly what install added
```

**1. Safety hook** - blocks destructive commands before they run, for
*every* Claude Code session on the machine (not just ones launched via
`yantra`):

- `rm -rf` / `Remove-Item -Recurse` - file deletion
- `git reset --hard` - discard work
- `git rebase -i` - interactive rebase
- `DELETE FROM` / `DROP TABLE` / `truncate table` - database operations
- `git push --force` - force push

Implemented as a real `PreToolUse` command hook
(`hooks/safety_gates.js`, speaking Claude Code's actual stdin-JSON /
stdout-JSON hook protocol) - not a Yantra-side wrapper. It fails **open** on
any parse error or unexpected input, on purpose: a bug in it should never be
able to silently block every tool call.

**2. `context-analysis` skill** - summarizes git branch, status, and
uncommitted changes. Invoke with `/context-analysis`, or Claude loads it
automatically when relevant. As a skill (not a hook that fires on every
tool call), it costs zero tokens until actually used - the right fit for a
project about *cutting* token usage.

Both are global, user-level changes (`~/.claude/settings.json` and
`~/.claude/skills/`) - deliberately **not** run automatically by `yantra
setup` or a normal launch. `install`/`uninstall` show you exactly what
they're about to change and ask for confirmation first (`-y` to skip the
prompt), and never touch any other hooks or skills already in your config.

---

## Environment Variables

Yantra doesn't require any credentials or environment variables of its own -
Claude CLI and Headroom each handle their own authentication.

Optional custom environment variables can be set in `yantra.config.json`'s
`environment` block for injection into the launched Claude session.

---

## Dependencies

**Zero external dependencies for Yantra itself** - Headroom (optional,
`yantra setup`) is the one exception, and it's a separate package Yantra
just resolves and shells out to.

Uses only Python standard library:
- `argparse` (CLI)
- `subprocess` (process management)
- `pathlib` (cross-platform paths)
- `json` (config parsing)

Requires Python 3.11+ and Node.js 20+ (for Claude CLI).

---

## Testing

```bash
python -m unittest discover -s tests -v
```

Also zero extra dependencies - `unittest` is standard library, same
philosophy as the rest of the project. Runs automatically on Windows,
Linux, and macOS via GitHub Actions on every push (see the badge at the
top). Covers the pure logic: config loading, `_build_launch_command()`'s
priority resolution (the most important piece of business logic in this
codebase - decides Headroom-wrapped vs plain launch), the hook-merge
idempotency logic behind `yantra install`/`uninstall`, and the real
`safety_gates.js` hook script via `node` (not a mock of its behavior - the
actual script, fed real stdin JSON, exactly as Claude Code would).

Doesn't cover a live end-to-end `yantra` launch against real Claude/
Headroom - that needs credentials CI doesn't have, and is still manually
verified (see the real measured numbers in
[Configuration](#configuration)).

---

## Troubleshooting

### "Claude CLI not found"
```bash
Install Claude: https://github.com/anthropics/claude-code
```

### "Node.js version too old"
```bash
Install Node.js 20+: https://nodejs.org/
```

### Headroom fails to start with a `litellm`/pricing error (Windows)

```
Error: Proxy exited with code 1: ...litellm_pricing.py...
AttributeError: module 'litellm' has no attribute 'model_cost'
```

Windows' legacy 260-character `MAX_PATH` limit, combined with Microsoft
Store Python's long install path (~124 characters before any package name)
and `litellm`'s deeply nested guardrail test fixtures, can silently corrupt
the install - files like `litellm`'s own `__init__.py` never get written,
so it imports as an empty namespace package. This isn't specific to one
machine; it hits any Windows user on Store Python with long paths disabled
(the Windows default).

Fixed as of this version: `yantra setup` installs Headroom into a dedicated
short-path venv (`~/.yantra/venv`) on Windows instead, which sidesteps the
limit entirely - no admin rights needed. If you hit this on an older
checkout, just re-run `python yantra.py setup`.

### Headroom proxy crashes with "An Application Control policy has blocked this file" (Windows)

```
Error: Proxy exited with code 1: ...error_detection.py...
ImportError: DLL load failed while importing _core: An Application Control
policy has blocked this file.
```

Windows 11's **Smart App Control** (enforced by default on clean installs)
blocks Headroom's compiled Rust extension (`headroom/_core.pyd`) because it
isn't yet trusted/signed to Smart App Control's satisfaction - a Headroom
packaging issue, not a Yantra bug, and not fixable in this repo. Smart App
Control itself is a one-way setting (disabling it requires reinstalling
Windows to turn back on), so don't disable it over this.

Fixed as of this version: Yantra sets `HEADROOM_REQUIRE_RUST_CORE=false` in
the launched session's environment automatically (documented in Headroom's
own troubleshooting guide) - this makes the native-extension failure
non-fatal instead of crashing the proxy. Verified working: the proxy starts
and reports healthy with this set, even with Smart App Control enforced.

### Authentication issues
If Yantra doesn't open the browser automatically:
1. Manually visit https://claude.ai
2. Log in to your Claude account
3. Return to the terminal and press Enter

### Verbose debugging
```bash
yantra -v
```

Shows detailed initialization and context injection info.

---

## Roadmap

### v0.1 (Current) ✅
- Session launcher, cross-platform (`yantra` command)
- Token optimization via Headroom, verified with real measured savings
- Safety hook + context-analysis skill, registered natively with Claude Code
- Config + CLI toggles for everything optional
- Automated tests + CI on Windows/Linux/macOS for the pure logic

### v0.2 (Next)
- Real macOS/Linux end-to-end validation (not just unit tests) - see
  [Status & Limitations](#status--limitations)
- Multi-turn cache-reuse measurement (does Headroom's cost benefit
  amortize over a long session? - open question, see Configuration)
- Additional native skills

### v1.0 (Future - once the above is validated)
- Multi-agent orchestration
- Subagent delegation

### v2.0 (Long-term)
- Production deployment
- Monitoring/observability

---

## Contributing

Contributions welcome! Please:
1. Follow code style (type hints, docstrings)
2. Add tests for new features
3. Update documentation
4. Submit PR with clear description

---

## License

MIT License - See LICENSE file for details

---

## Author

**Ravi Teja Gutakonda**  
Sr. QA Engineer → AI/ML Engineer  
Email: gutti.raviteja4@gmail.com

---

Run `yantra -h` for help. See [Status & Limitations](#status--limitations)
above before relying on this for anything important.
