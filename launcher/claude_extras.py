"""Installs Yantra's safety-gate hooks and skills directly into Claude
Code's own native config - not Yantra's subprocess wrapper.

Claude Code already has real mechanisms for this (hooks via
~/.claude/settings.json, skills via ~/.claude/skills/) that are more capable
than anything Yantra could bolt on by injecting a system prompt through a
subprocess call. This module registers Yantra's pieces with those real
mechanisms instead of reinventing them.

Auto-discovers whatever's currently under hooks/ and skills/ - drop a new
`.js` file in hooks/, or a new `<name>/SKILL.md` under skills/, and the next
`yantra install` picks it up with no code changes here. install() also
prunes anything it previously registered that's no longer on disk (a hook
or skill renamed or deleted from the repo), so re-running it keeps
~/.claude/ in sync with this repo rather than just accumulating entries.

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
HOOKS_SOURCE_DIR = PROJECT_ROOT / "hooks"
SKILLS_SOURCE_DIR = PROJECT_ROOT / "skills"

CLAUDE_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
SKILLS_INSTALL_DIR = Path.home() / ".claude" / "skills"
# Tracks which skill directories under SKILLS_INSTALL_DIR Yantra put there,
# so uninstall/resync only ever touches skills Yantra actually installed -
# never anything a user added by hand. Hooks don't need an equivalent: a
# hook handler's own path (under HOOKS_SOURCE_DIR) is enough to identify it.
SKILLS_MANIFEST_PATH = SKILLS_INSTALL_DIR / ".yantra-manifest.json"

# Both tool names Yantra's safety gates should guard - Bash and PowerShell,
# matching the tools this harness actually exposes.
GUARDED_MATCHERS = ["Bash", "PowerShell"]


def find_node_executable() -> Optional[str]:
    """Locate the Node.js executable (required to run hook scripts)."""
    return shutil.which("node")


def discover_hooks() -> List[Path]:
    """Every `.js` file directly under hooks/ - each becomes a PreToolUse
    guard on GUARDED_MATCHERS. Not recursive; sorted for stable output."""
    if not HOOKS_SOURCE_DIR.is_dir():
        return []
    return sorted(HOOKS_SOURCE_DIR.glob("*.js"))


def discover_skills() -> List[Path]:
    """Every subdirectory of skills/ that contains a SKILL.md."""
    if not SKILLS_SOURCE_DIR.is_dir():
        return []
    return sorted(
        d for d in SKILLS_SOURCE_DIR.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    )


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


def _build_hook_handler(node_path: str, hook_script: Path) -> Dict[str, Any]:
    """The command-hook entry Yantra registers for one hook script."""
    return {
        "type": "command",
        "command": node_path,
        "args": [str(hook_script)],
    }


def _is_yantra_handler(handler: Dict[str, Any]) -> bool:
    """Identify a hook-handler entry as one Yantra installed.

    Matched by whether any of its args is a script whose parent directory
    is this repo's hooks/ - path-based, not name-based, so it still
    recognizes (and can clean up) a hook after the underlying file is
    renamed or deleted from the repo, without needing a separate manifest
    the way skills do.
    """
    hooks_dir = HOOKS_SOURCE_DIR.resolve()
    for arg in handler.get("args") or []:
        try:
            if Path(str(arg)).resolve().parent == hooks_dir:
                return True
        except OSError:
            continue
    return False


def _sync_hooks(settings: Dict[str, Any], hook_scripts: List[Path], node_path: str) -> None:
    """Make settings["hooks"]["PreToolUse"] match hook_scripts exactly.

    Replaces every Yantra-registered handler with the current set of
    scripts under hooks/ - added, removed, or renamed files are all
    reflected here, not just whatever was there on the first install.
    Every other hook already in settings.json (not Yantra's) is untouched.
    """
    settings.setdefault("hooks", {})
    pre_tool_use: List[Dict[str, Any]] = settings["hooks"].setdefault("PreToolUse", [])

    fresh_handlers = [_build_hook_handler(node_path, script) for script in hook_scripts]

    for matcher in GUARDED_MATCHERS:
        group = next((g for g in pre_tool_use if g.get("matcher") == matcher), None)
        if group is None:
            if not fresh_handlers:
                continue
            group = {"matcher": matcher, "hooks": []}
            pre_tool_use.append(group)
        group["hooks"] = [h for h in group.get("hooks", []) if not _is_yantra_handler(h)] + fresh_handlers

    # Drop matcher groups that end up with no hooks left at all (e.g. every
    # hook under hooks/ was removed since the last install).
    settings["hooks"]["PreToolUse"] = [g for g in pre_tool_use if g.get("hooks")]


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
        # else: group only had Yantra's handler(s) - drop the whole group

    settings["hooks"]["PreToolUse"] = kept_groups
    return removed


def _load_skills_manifest() -> List[str]:
    if not SKILLS_MANIFEST_PATH.exists():
        return []
    try:
        data = json.loads(SKILLS_MANIFEST_PATH.read_text())
    except json.JSONDecodeError:
        return []
    return data.get("installed_skills", [])


def _save_skills_manifest(names: List[str]) -> None:
    SKILLS_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    SKILLS_MANIFEST_PATH.write_text(
        json.dumps({"installed_skills": sorted(names)}, indent=2) + "\n"
    )


def _sync_skills(skill_dirs: List[Path]) -> List[str]:
    """Copy every current skill in skills/ into ~/.claude/skills/, and
    remove any skill Yantra installed previously that's no longer in the
    repo (renamed or deleted) - per the manifest, never touching a skill
    Yantra didn't put there itself.

    Returns:
        The names of skills present after this sync (possibly empty).
    """
    previous = set(_load_skills_manifest())
    current_names = [d.name for d in skill_dirs]

    for stale_name in previous - set(current_names):
        stale_path = SKILLS_INSTALL_DIR / stale_name
        if stale_path.exists():
            shutil.rmtree(stale_path)

    if skill_dirs:
        SKILLS_INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    for skill_dir in skill_dirs:
        dest = SKILLS_INSTALL_DIR / skill_dir.name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(skill_dir, dest)

    if current_names or previous:
        _save_skills_manifest(current_names)

    return current_names


def _remove_skills() -> List[str]:
    """Remove every skill Yantra installed, per the manifest.

    Returns:
        The names of skills actually removed.
    """
    names = _load_skills_manifest()
    for name in names:
        path = SKILLS_INSTALL_DIR / name
        if path.exists():
            shutil.rmtree(path)
    if SKILLS_MANIFEST_PATH.exists():
        SKILLS_MANIFEST_PATH.unlink()
    return names


def describe_install() -> str:
    """Human-readable preview of exactly what `install()` will do."""
    node_path = find_node_executable() or "<node not found - install will fail>"
    hook_scripts = discover_hooks()
    skill_dirs = discover_skills()

    lines = [
        "This will make global changes, affecting every Claude Code",
        "session on this machine (not just ones launched via `yantra`):",
        "",
        f"1. Register {len(hook_scripts)} PreToolUse hook(s) in:",
        f"   {CLAUDE_SETTINGS_PATH}",
        f"   Matchers: {', '.join(GUARDED_MATCHERS)}",
    ]
    for script in hook_scripts:
        lines.append(f"   - {node_path} {script}")

    lines += [
        "",
        f"2. Install {len(skill_dirs)} skill(s) into:",
        f"   {SKILLS_INSTALL_DIR}",
    ]
    for skill_dir in skill_dirs:
        lines.append(f"   - {skill_dir.name}")

    lines += [
        "",
        "Both are reversible with `yantra uninstall`. Re-running `yantra",
        "install` later picks up anything added to, removed from, or",
        "renamed in this repo's hooks/ and skills/ folders since the last",
        "run. Any other hooks or skills already in your Claude Code config",
        "are left untouched.",
    ]
    return "\n".join(lines)


def install() -> int:
    """Register every hook in hooks/ and install every skill in skills/.

    Safe to re-run - syncs to whatever's currently in those folders,
    including removing entries for anything since deleted or renamed.

    Returns:
        0 on success, 1 on failure
    """
    node_path = find_node_executable()
    if not node_path:
        print(
            "❌ Node.js not found in PATH - required to run hook scripts. "
            "Install Node.js 20+ first: https://nodejs.org/",
            file=sys.stderr,
        )
        return 1

    hook_scripts = discover_hooks()
    skill_dirs = discover_skills()

    try:
        settings = _load_settings()
    except ValueError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1

    _sync_hooks(settings, hook_scripts, node_path)
    _save_settings(settings)
    if hook_scripts:
        names = ", ".join(s.name for s in hook_scripts)
        print(f"✓ {len(hook_scripts)} hook(s) registered in {CLAUDE_SETTINGS_PATH}: {names}")
    else:
        print("ℹ  No hooks found in hooks/ - any previously registered Yantra hooks were removed.")

    installed_skills = _sync_skills(skill_dirs)
    if installed_skills:
        print(f"✓ {len(installed_skills)} skill(s) installed at {SKILLS_INSTALL_DIR}: {', '.join(installed_skills)}")
    else:
        print("ℹ  No skills found in skills/ - any previously installed Yantra skills were removed.")

    print(
        "\n✅ Done. Applies the next time you start a Claude Code session "
        "(this one, and any other project). Verify with `/hooks` and "
        "`/skills` inside Claude, or `yantra uninstall` to remove."
    )
    return 0


def describe_uninstall() -> str:
    return (
        f"This will remove every hook Yantra registered from\n"
        f"  {CLAUDE_SETTINGS_PATH}\n"
        f"and every skill Yantra installed under\n"
        f"  {SKILLS_INSTALL_DIR}\n"
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
        print(f"✓ Hook(s) removed from {CLAUDE_SETTINGS_PATH}")
    else:
        print("ℹ  No Yantra hooks were registered - nothing to remove there.")

    removed_skills = _remove_skills()
    if removed_skills:
        print(f"✓ {len(removed_skills)} skill(s) removed from {SKILLS_INSTALL_DIR}: {', '.join(removed_skills)}")
    else:
        print("ℹ  No Yantra skills were installed - nothing to remove there.")

    print("\n✅ Done.")
    return 0
