# Architecture & Design Decisions

How Yantra actually works, and why each non-obvious decision exists. The
README tells you *what* to run; this document tells you *why* it's built
this way — written for whoever ends up defending or extending this code,
including a future version of the person reading it.

## 1. What actually happens when you run `yantra`

```
yantra (shell stub) → python yantra.py → SessionLauncher.initialize() → start_interactive_session()
```

`yantra` / `yantra.bat` are deliberately dumb one-line passthroughs to
`python yantra.py` — see [§6](#6-two-shell-stubs-not-one-cross-platform-script)
for why there are two of them instead of one.

`initialize()` runs four steps:

1. **`ConfigLoader.load()`** reads `config/yantra.config.json` from a path
   anchored to `yantra.py`'s own file location
   (`Path(__file__).resolve().parent / "config"`), **not** the caller's
   `cwd`. See [§2](#2-config-resolves-relative-to-the-script-not-cwd).
2. **`EnvironmentValidator.validate_all()`** checks Node.js, Claude CLI,
   Headroom. Node/Claude failures are fatal (`issues`, block the launch);
   a missing Headroom is only a `warning` — Headroom is optional by
   design and must never block a launch.
3. **`ContextInjector.inject_context()`** gathers git branch, cwd, system
   info. **This is printed to your terminal for you to see. It is never
   sent to Claude.** Don't confuse this with prompt injection — nothing
   here reaches the model. Real context delivery to Claude goes through
   Claude Code's own native mechanisms (`CLAUDE.md`, skills) — see
   [§6](#6-hooks--skills-are-registered-natively-not-injected-via-subprocess).
4. **`HookManager.load_hooks()`** reads `hooks.json` for a console summary
   and validation only. It does **not** register anything with Claude
   Code — that's a separate, explicit step (`yantra install`).

Then `_build_launch_command()` — the single most important function in
the codebase — decides the actual subprocess command, and
`subprocess.run()` launches it with `_build_claude_environment()`'s env
dict merged in.

## 2. Config resolves relative to the script, not cwd

The original implementation used `Path.cwd()` as the config directory
default. That's a real bug, not a style choice: since `yantra` is
installed on `PATH` specifically to be run from *any* directory, using
`cwd` meant config silently never loaded once you were no longer standing
in the project folder. Caught by actually testing a launch from an
unrelated directory, not by reading the code — the kind of bug that looks
completely fine until you run it somewhere else.

Fix: `DEFAULT_CONFIG_DIR = Path(__file__).resolve().parent / "config"` in
`yantra.py`, so resolution is anchored to where the script physically
lives, independent of the caller's cwd.

## 3. `claude.cmd` path resolution (Windows)

On Windows, npm installs Claude CLI as `claude.cmd`, not `claude.exe`.
`subprocess.run(["claude"])` throws `WinError 2` — Windows can't execute a
bare name that resolves to a `.cmd` shim without the extension, even
though `shutil.which("claude")` resolves it fine. This silently broke the
plain-Claude fallback path whenever Headroom was disabled or missing —
exactly the safety net that's supposed to guarantee `yantra` never fails
to launch *something*.

Fix: always resolve the full path via `shutil.which()` before passing it
to `subprocess.run()`, in both `validator.py`'s Claude CLI check and
`session.py`'s fallback command builder. Never pass the bare string
`"claude"` to `subprocess.run()`.

*Anticipated question: "why not just use `shell=True`?"* — Works too, but
resolving the explicit path is more portable across platforms and avoids
adding shell-injection surface to a command built from config values.

## 4. Headroom installs into a dedicated venv on Windows

Root cause: Windows' legacy 260-character `MAX_PATH` limit. Microsoft
Store Python's install path already consumes ~124 characters before any
package name is even appended. Combined with `litellm`'s deeply-nested
guardrail test fixtures (a Headroom dependency), some files — including
`litellm`'s own `__init__.py` — silently failed to write during
`pip install`. Confirmed by computing the exact failing path length: it
landed at precisely 260 characters, the failure boundary. The install
reported success; the package was actually broken (imported as an empty
namespace package, `litellm.model_cost` didn't exist).

This isn't a one-off — the Microsoft Store Python prefix length is fixed
regardless of username, so **any** Windows user on Store Python with long
paths disabled (the Windows default; enabling it requires admin rights)
hits the same failure.

Fix: on Windows, `yantra setup` creates a dedicated venv at
`~/.yantra/venv` (short path, no admin needed) and installs Headroom
there instead of into the ambient Python's site-packages. Measured: the
same file's path dropped from 260 → 167 characters after the fix.
`find_headroom_executable()` in `validator.py` checks this venv location
*first*, ahead of `PATH`, specifically so a stale/broken global install
never gets picked up over the working one.

## 5. `HEADROOM_REQUIRE_RUST_CORE=false` is always set

Headroom ships a compiled Rust extension (`_core.pyd`) for its
error-detection logic — no pure-Python fallback exists; it's an
unconditional import. Windows 11's Smart App Control (enforced by default
on clean installs) blocked it outright as an untrusted/unsigned binary —
a Headroom packaging/signing issue, unrelated to anything in this repo,
and not fixable here.

Smart App Control itself is a one-way OS setting: disabling it requires
reinstalling Windows to turn back on. That was never a serious option.

Fix: Headroom's own troubleshooting docs name the escape hatch —
`HEADROOM_REQUIRE_RUST_CORE=false` makes the native-extension failure
non-fatal instead of crashing the proxy. Set unconditionally in
`_build_claude_environment()`; it's a harmless no-op whenever Headroom
isn't actually in the launch command, so there's no cost to always
setting it. Verified: the proxy starts and its `/health` endpoint reports
healthy with this set, even with Smart App Control enforced.

## 6. `--no-mcp` is the default Headroom flag

Headroom auto-registers its own MCP tools (`headroom_compress`,
`headroom_retrieve`, `headroom_stats`) on every session by default. Their
tool schemas get billed as real tokens on *every single request*, whether
or not you ever call them.

Measured directly (`claude -p ... --output-format json`, real billed
usage, not an estimate) on a trivial prompt with nothing to compress:

| | Cost | Input tokens |
|---|---:|---:|
| Plain `claude` | $0.0253 | 2 |
| `headroom wrap claude` (default) | $0.0527 | 2,814 |
| `headroom wrap claude --no-mcp` | $0.0222 | 2,814 |

`--no-mcp` removes the fixed MCP overhead, landing *below* the unwrapped
baseline. `input_tokens` staying at 2,814 either way shows a second,
smaller, separate fixed cost remains regardless of `--no-mcp` — Headroom's
own `--tool-search` docs name this one explicitly (upstream issue #746):
routing through a custom proxy URL disrupts Claude Code's normal
tool-schema cache lineage.

**The honest trade-off:** `--no-mcp` gives up `headroom_retrieve` — the
ability for Claude to recover original content if Headroom's compression
was ever lossy enough to matter. That failure mode is untested, not
disproven. The default was chosen because the cost of MCP is proven and
constant, while the benefit it hedges against is unverified. If you want
it back: `"args": []` in `yantra.config.json`.

## 7. Hooks & skills are registered natively, not injected via subprocess

The original design tried to build a custom system-prompt/context/hooks
pipeline through Yantra's own subprocess wrapper — gather git context,
assemble it into a system prompt string, pass it to Claude somehow. It
never actually worked (the assembly code existed; nothing called it), and
investigating *why* led to a bigger realization: **Claude Code already has
real, better mechanisms for all of this.**

- Real context: Claude Code can just run `git status` itself, live,
  whenever it needs to — more accurate than a stale snapshot injected at
  launch time.
- Real safety: Claude Code has its own interactive permission system
  already, plus a documented `PreToolUse` hook protocol (stdin JSON in,
  stdout JSON decision out) for programmatic blocking.
- Real custom instructions: `CLAUDE.md`, auto-loaded, no subprocess
  wrapping required.
- Real on-demand knowledge: Skills (`~/.claude/skills/`), which load only
  when actually used — unlike a hook or injected prompt that costs tokens
  on every single turn.

Rebuilding a worse version of all this inside a subprocess wrapper would
have been pure waste. Instead, `yantra install` registers exactly two
things directly with Claude Code's real config:

1. **`hooks/safety_gates.js`** — a real `PreToolUse` command hook,
   speaking Claude Code's actual protocol (verified against official docs,
   not guessed): reads JSON on stdin, writes a JSON decision to stdout,
   exits 0. Registered in `~/.claude/settings.json`. Fails **open** on any
   parse error or unexpected input — a bug in it must never be able to
   silently block every tool call globally.
2. **`skills/context-analysis/SKILL.md`** — a real Claude Code skill,
   using the documented `` !`command` `` dynamic-context-injection syntax.
   Installed to `~/.claude/skills/`. Loads on demand, not on every turn —
   the right fit for a project about *cutting* token usage, not adding to
   it.

Both are **global, user-level changes** — they affect every Claude Code
session on the machine, not just ones launched via `yantra`. That's
deliberate (Yantra is meant to enhance Claude Code everywhere), but it
also means `install`/`uninstall` are separate, explicit, confirmed steps
— never run implicitly by `setup` or a normal launch. They preview the
exact change and ask before touching your global config, and never touch
any other hooks/skills already there (verified: idempotent re-install,
non-destructive to unrelated entries, tested against an isolated fake
`~/.claude` before ever running for real).

## 8. Two shell stubs, not one cross-platform script

`yantra.bat` (Windows) and `yantra` (macOS/Linux) both exist because the
OS dispatch layer makes a single universal launcher file impossible:
Windows only resolves a bare command name like `yantra` to a
`.exe`/`.bat`/`.cmd`/`.ps1`; Unix shells only resolve it to an
extensionless file with a shebang and the executable bit set. That's a
hard OS-level constraint, not a design choice.

Both stubs are intentionally *thin* — pure passthroughs
(`python yantra.py %*` / `python3 yantra.py "$@"`) with zero logic of
their own. All actual behavior (`setup`, `install`, launch defaults, flag
handling) lives in `yantra.py`, which is one Python file that runs
identically on every OS. This was a deliberate simplification: an earlier
version had each stub hardcoding `launch yantra` and juggling flag
ordering — fragile and duplicated. Pushing everything into the one Python
entry point means the stubs can never drift out of sync with each other.

## 9. Token/caching mechanics — the model behind the cost numbers

Useful background for defending the "sometimes worse, sometimes 44%
better" results: Anthropic bills tokens in four buckets, not one.

| Bucket | Relative price | Meaning |
|---|---:|---|
| `input_tokens` | 1x | Genuinely new content |
| `cache_creation_input_tokens` | ~1.25–2x | New content you're asking to be cached for next time |
| `cache_read_input_tokens` | ~0.1x | Content that exactly matches something already cached |
| `output_tokens` | highest | What the model generates |

Caching is **content-hash-based**, not route-based: Anthropic hashes the
request prefix (system prompt → tools → history) up to a cache breakpoint
and checks for an exact byte match within the TTL window (5 min or 1
hour). Any change to those bytes — even from a proxy adding/removing tool
schemas or restructuring content — breaks the match for everything after
that point, forcing a fresh (expensive) `cache_creation` or `input_tokens`
instead of a cheap `cache_read`.

This is *why* Headroom's compression and Anthropic's caching can pull in
opposite directions: compression can shrink total content (fewer tokens
overall) while simultaneously changing the request bytes enough to break
an otherwise-free cache hit (a worse price-tier mix). Both effects were
observed and measured separately in real tests — see the README's
Configuration section for the exact numbers.

## FAQ — questions likely to come up

**"Is routing my Anthropic traffic through an unofficial local proxy
safe?"** The proxy runs locally (`127.0.0.1`) and relays to the real
Anthropic API — it's not intercepting traffic remotely. It is still a
third-party dependency in the request path; `--no-headroom`, or simply
not running `yantra setup`, opts out completely with zero functional
loss elsewhere.

**"Why not just rely on Claude Code's built-in prompt caching instead of
Headroom?"** They're not alternatives — Headroom's compression happens
*before* Anthropic ever tokenizes the request; caching happens *after*,
server-side, based on exact byte match. See [§9](#9-tokencaching-mechanics--the-model-behind-the-cost-numbers).

**"Is the safety hook real security?"** No — it's regex pattern-matching
on shell commands, straightforward to bypass with a slightly different
phrasing of the same command. It's a convenience guardrail against
typos/carelessness, not a security boundary. Documented as such in the
README on purpose.

**"How do I know the 44% number isn't cherry-picked?"** It isn't hidden
that it's a single result — the README documents the *worse* result too
(trivial prompts show a net loss) and explains the mechanism behind both.
Small sample, real measured numbers (not estimates), mechanism explained,
never presented as a benchmark suite.

**"What's actually tested vs. just claimed?"** See the README's
[Status & Limitations](README.md#status--limitations) section and
[Testing](README.md#testing) section — 89 unit tests cover the pure logic
and run in CI on Windows/Linux/macOS; end-to-end launches against real
Claude/Headroom are manually verified, not automated (they'd need live
credentials CI doesn't have).
