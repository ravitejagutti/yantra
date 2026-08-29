"""Installs Yantra's safety-gate hook and context-analysis skill directly
into Claude Code's own native config - not Yantra's subprocess wrapper.

Claude Code already has real mechanisms for this (hooks via
~/.claude/settings.json, skills via ~/.claude/skills/) that are more capable
than anything Yantra could bolt on by injecting a system prompt through a
subprocess call. This module registers Yantra's two pieces with those real
mechanisms instead of reinventing them.

Both install() and uninstall() are global, user-level changes - they affect
every Claude Code session on this machine, not just ones launched via
`yantra`. That's deliberate (Yantra is meant to enhance Claude Code
everywhere, not just from within this project), but it also means these are
never called implicitly during a normal `yantra` launch - only when the user
explicitly runs `yantra install` / `yantra uninstall`, previews the exact
change, and confirms it.
"""

import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HOOK_SCRIPT_PATH = PROJECT_ROOT / "hooks" / "safety_gates.js"
SKILL_SOURCE_PATH = PROJECT_ROOT / "skills" / "context-analysis" / "SKILL.md"

CLAUDE_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
SKILL_INSTALL_PATH = Path.home() / ".claude" / "skills" / "context-analysis" / "SKILL.md"

# Both tool names Yantra's safety gate should guard - Bash and PowerShell,
# matching the tools this harness actually exposes.
GUARDED_MATCHERS = ["Bash", "PowerShell"]


def find_node_executable() -> Optional[str]:
    """Locate the Node.js executable (required to run the hook script)."""
    return shutil.which("node")


def _load_settings() -> Dict[str, Any]:
    """Load ~/.claude/settings.json, or {} if it doesn't exist yet.

    Raises:
        ValueError: If the file exists but isn't valid JSON - we refuse to
            touch a settings file we can't parse, rather than risk
            clobbering something the user hand-edited.
    """
    if not CLAUDE_SETTINGS_PATH.exists():
        return {}

    try:
        return json.loads(CLAUDE_SETTINGS_PATH.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(
            f"{CLAUDE_SETTINGS_PATH} exists but isn't valid JSON ({e}). "
            "Fix or back it up before running `yantra install`."
        )


def _save_settings(settings: Dict[str, Any]) -> None:
    CLAUDE_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CLAUDE_SETTINGS_PATH.write_text(json.dumps(settings, indent=2) + "\n")


def _build_hook_handler(node_path: str) -> Dict[str, Any]:
    """The single command-hook entry Yantra registers for each matcher."""
    return {
        "type": "command",
        "command": node_path,
        "args": [str(HOOK_SCRIPT_PATH)],
    }


def _is_yantra_handler(handler: Dict[str, Any]) -> bool:
    """Identify a hook-handler entry as one Yantra previously installed.

    Matched by the hook script's absolute path appearing in args - this is
    how re-running `install` replaces a stale copy instead of duplicating
    it, and how `uninstall` finds exactly what to remove without touching
    any other hooks already in settings.json.
    """
    args = handler.get("args") or []
    return str(HOOK_SCRIPT_PATH) in args


def _merge_hook(settings: Dict[str, Any], matcher: str, handler: Dict[str, Any]) -> None:
    """Add/replace Yantra's handler under `matcher` in settings["hooks"]["PreToolUse"].

    Preserves every other hook already registered - only touches entries
    that are ours (see _is_yantra_handler), in the specific matcher group.
    """
    settings.setdefault("hooks", {})
    pre_tool_use: List[Dict[str, Any]] = settings["hooks"].setdefault("PreToolUse", [])

    for group in pre_tool_use:
        if group.get("matcher") == matcher:
            group["hooks"] = [h for h in group.get("hooks", []) if not _is_yantra_handler(h)]
            group["hooks"].append(handler)
            return

    pre_tool_use.append({"matcher": matcher, "hooks": [handler]})


def _remove_hook(settings: Dict[str, Any]) -> bool:
    """Remove every Yantra-installed handler from settings["hooks"]["PreToolUse"].

    Drops now-empty matcher groups. Leaves everything else untouched.

    Returns:
        True if anything was actually removed.
    """
    pre_tool_use = settings.get("hooks", {}).get("PreToolUse")
    if not pre_tool_use:
        return False

    removed = False
    kept_groups = []

    for group in pre_tool_use:
        hooks = group.get("hooks", [])
        filtered = [h for h in hooks if not _is_yantra_handler(h)]
        if len(filtered) != len(hooks):
            removed = True
        if filtered:
            group["hooks"] = filtered
            kept_groups.append(group)
        # else: group only had Yantra's handler - drop the whole group

    settings["hooks"]["PreToolUse"] = kept_groups
    return removed


def describe_install() -> str:
    """Human-readable preview of exactly what `install()` will do."""
    node_path = find_node_executable() or "<node not found - install will fail>"
    lines = [
        "This will make two global changes, affecting every Claude Code",
        "session on this machine (not just ones launched via `yantra`):",
        "",
        f"1. Register a PreToolUse safety hook in:",
        f"   {CLAUDE_SETTINGS_PATH}",
        f"   Matchers: {', '.join(GUARDED_MATCHERS)}",
        f"   Command:  {node_path} {HOOK_SCRIPT_PATH}",
        f"   Blocks: rm -rf, git reset --hard, git rebase -i, DELETE FROM,",
        f"           DROP TABLE, truncate table, git push --force",
        "",
        f"2. Install a context-analysis skill at:",
        f"   {SKILL_INSTALL_PATH}",
        f"   Invoke manually with /context-analysis, or Claude loads it",
        f"   automatically when relevant. Summarizes git branch/status on",
        f"   demand - costs nothing unless actually used.",
        "",
        "Both are reversible with `yantra uninstall`. Any other hooks or",
        "skills already in your Claude Code config are left untouched.",
    ]
    return "\n".join(lines)


def install() -> int:
    """Register the safety hook and install the context-analysis skill.

    Returns:
        0 on success, 1 on failure
    """
    node_path = find_node_executable()
    if not node_path:
        print(
            "❌ Node.js not found in PATH - required to run the safety-gate "
            "hook. Install Node.js 20+ first: https://nodejs.org/",
            file=sys.stderr,
        )
        return 1

    if not HOOK_SCRIPT_PATH.exists():
        print(f"❌ Hook script not found: {HOOK_SCRIPT_PATH}", file=sys.stderr)
        return 1

    if not SKILL_SOURCE_PATH.exists():
        print(f"❌ Skill source not found: {SKILL_SOURCE_PATH}", file=sys.stderr)
        return 1

    try:
        settings = _load_settings()
    except ValueError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1

    handler = _build_hook_handler(node_path)
    for matcher in GUARDED_MATCHERS:
        _merge_hook(settings, matcher, handler)
    _save_settings(settings)
    print(f"✓ Safety hook registered in {CLAUDE_SETTINGS_PATH}")

    SKILL_INSTALL_PATH.parent.mkdir(parents=True, exist_ok=True)
    SKILL_INSTALL_PATH.write_text(SKILL_SOURCE_PATH.read_text())
    print(f"✓ context-analysis skill installed at {SKILL_INSTALL_PATH}")

    print(
        "\n✅ Done. Both apply the next time you start a Claude Code session "
        "(this one, and any other project). Verify with `/hooks` and "
        "`/skills` inside Claude, or `yantra uninstall` to remove."
    )
    return 0


def describe_uninstall() -> str:
    return (
        f"This will remove Yantra's PreToolUse safety hook from\n"
        f"  {CLAUDE_SETTINGS_PATH}\n"
        f"and delete the installed skill at\n"
        f"  {SKILL_INSTALL_PATH}\n"
        f"Any other hooks or skills are left untouched."
    )


def uninstall() -> int:
    """Remove exactly what install() added. Safe to run if never installed.

    Returns:
        0 on success (including "nothing to remove"), 1 on failure
    """
    try:
        settings = _load_settings()
    except ValueError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1

    removed_hook = _remove_hook(settings)
    if removed_hook:
        _save_settings(settings)
        print(f"✓ Safety hook removed from {CLAUDE_SETTINGS_PATH}")
    else:
        print("ℹ  No Yantra safety hook was registered - nothing to remove there.")

    if SKILL_INSTALL_PATH.exists():
        SKILL_INSTALL_PATH.unlink()
        # Clean up the now-empty skill directory, if it's empty.
        try:
            SKILL_INSTALL_PATH.parent.rmdir()
        except OSError:
            pass  # not empty (user added files) - leave it
        print(f"✓ context-analysis skill removed from {SKILL_INSTALL_PATH}")
    else:
        print("ℹ  No context-analysis skill was installed - nothing to remove there.")

    print("\n✅ Done.")
    return 0
