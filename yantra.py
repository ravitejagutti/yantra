#!/usr/bin/env python3

"""Yantra v1 - Enhanced Claude Sessions with Context & Safety.

Session launcher that provides:
- Context injection (git, system state)
- Safety gates (block destructive ops)
- Configurable skills and hooks

Usage:
    python yantra.py                         # Launch enhanced Claude session
    python yantra.py -v                      # Verbose mode
    python yantra.py setup                   # One-time: install Headroom
    python yantra.py install                 # One-time: register safety hook + skill with Claude Code
    python yantra.py --help                  # Show this help
"""

import sys
import subprocess
import argparse
from pathlib import Path

from launcher import __version__
from launcher.session import SessionLauncher
from launcher import claude_extras
from launcher.validator import HEADROOM_VENV_DIR, get_headroom_venv_python

# Yantra's config/ folder, anchored to this script's own location - not the
# caller's cwd. `yantra` is meant to run from any directory (that's the
# whole point of putting it on PATH), so config resolution can't depend on
# where the user happened to be standing when they typed the command.
DEFAULT_CONFIG_DIR = Path(__file__).resolve().parent / "config"


def create_parser() -> argparse.ArgumentParser:
    """Create CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="yantra",
        description="Enhanced Claude sessions with context injection and safety gates",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python yantra.py                         # Launch enhanced Claude session
  python yantra.py -v                      # Verbose mode
  python yantra.py setup                   # One-time: install Headroom
  python yantra.py install                 # One-time: register safety hook + skill with Claude Code
  python yantra.py uninstall               # Remove what `install` registered
  python yantra.py --no-headroom           # Launch this run without Headroom
  python yantra.py --headroom              # Force Headroom on, even if disabled in config
  python yantra.py launch yantra           # Same as the bare command above
  python yantra.py --help                  # Show this help

Works in: Terminal, PowerShell, cmd.exe, Bash
Docs: https://github.com/ravitejagutti/yantra
        """,
    )

    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "-c", "--config-dir",
        type=Path,
        help="Config directory (default: the config/ folder next to yantra.py)",
    )

    headroom_group = parser.add_mutually_exclusive_group()
    headroom_group.add_argument(
        "--headroom",
        dest="headroom_override",
        action="store_true",
        default=None,
        help="Force-enable Headroom token optimization for this run "
             "(overrides yantra.config.json)",
    )
    headroom_group.add_argument(
        "--no-headroom",
        dest="headroom_override",
        action="store_false",
        default=None,
        help="Disable Headroom token optimization for this run "
             "(overrides yantra.config.json)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command")

    # launch subcommand with target argument
    launch_parser = subparsers.add_parser("launch", help="Launch enhanced Claude session")
    launch_parser.add_argument(
        "target",
        choices=["yantra"],
        help="Launch target (yantra = enhanced Claude session)",
    )

    # setup subcommand - one-time Headroom install
    subparsers.add_parser(
        "setup",
        help="One-time setup: install Headroom for token optimization",
    )

    # install/uninstall - register the safety hook + context-analysis skill
    # directly with Claude Code (global, all projects, not just Yantra)
    install_parser = subparsers.add_parser(
        "install",
        help="Register Yantra's safety hook + context-analysis skill with Claude Code (global)",
    )
    install_parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Skip the confirmation prompt",
    )

    uninstall_parser = subparsers.add_parser(
        "uninstall",
        help="Remove the safety hook + skill installed by `yantra install`",
    )
    uninstall_parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Skip the confirmation prompt",
    )

    return parser


def _confirm(preview: str, skip_prompt: bool) -> bool:
    """Show a preview and ask for explicit confirmation before proceeding.

    Args:
        preview: Human-readable description of what's about to change
        skip_prompt: If True, skip the interactive prompt (--yes)

    Returns:
        True if the caller should proceed
    """
    print(preview)
    print()

    if skip_prompt:
        return True

    try:
        answer = input("Proceed? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False

    return answer in ("y", "yes")


def run_setup() -> int:
    """One-time setup: install Headroom for token optimization.

    Safe to re-run. Everything else in Yantra needs zero external
    dependencies - Headroom is the one optional piece, and Yantra falls
    back to launching Claude directly (no optimization) if it's missing.

    On Windows, installs into a dedicated venv (HEADROOM_VENV_DIR)
    at a short path rather than the ambient Python's site-packages - see the
    comment on HEADROOM_VENV_DIR in launcher/validator.py for why: Windows'
    legacy 260-char MAX_PATH can silently corrupt the install otherwise, and
    that's not specific to this machine - it hits any Windows user on
    Microsoft Store Python with long paths disabled (the Windows default).

    Returns:
        0 on success, 1 on failure
    """
    print("Installing Headroom (token optimization for Claude sessions)...\n")

    if sys.platform == "win32":
        venv_python = get_headroom_venv_python()

        if not venv_python.exists():
            print(f"Creating a short-path virtual environment at {HEADROOM_VENV_DIR}")
            print(
                "(Windows' MAX_PATH limit makes installing Headroom's own "
                "dependencies directly into Store Python's long install "
                "path unreliable - see README.)\n"
            )
            venv_result = subprocess.run(
                [sys.executable, "-m", "venv", str(HEADROOM_VENV_DIR)]
            )
            if venv_result.returncode != 0:
                print("\n❌ Failed to create the virtual environment.", file=sys.stderr)
                return 1

        pip_cmd = [str(venv_python), "-m", "pip", "install", "headroom-ai[all]"]
    else:
        # macOS/Linux have no equivalent path-length limit - install directly.
        # sys.executable -m pip works the same regardless of whether the
        # platform calls it "pip" or "pip3", avoiding that OS-naming split.
        pip_cmd = [sys.executable, "-m", "pip", "install", "headroom-ai[all]"]

    result = subprocess.run(pip_cmd)

    if result.returncode != 0:
        print(
            "\n❌ Headroom install failed. Yantra will still work - it just "
            "launches Claude directly, without token optimization, until "
            "this succeeds.",
            file=sys.stderr,
        )
        return 1

    print('\n✅ Setup complete. Run "yantra" to launch.')
    return 0


def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        # Bare `yantra` / `python yantra.py` with no subcommand - default to
        # launching (the common case). Use --help to see the full command set.
        args.command = "launch"
        args.target = "yantra"

    if args.command == "setup":
        return run_setup()

    if args.command == "install":
        if not _confirm(claude_extras.describe_install(), args.yes):
            print("Cancelled.")
            return 130
        return claude_extras.install()

    if args.command == "uninstall":
        if not _confirm(claude_extras.describe_uninstall(), args.yes):
            print("Cancelled.")
            return 130
        return claude_extras.uninstall()

    config_dir = args.config_dir or DEFAULT_CONFIG_DIR

    try:
        launcher = SessionLauncher(
            config_dir=config_dir,
            verbose=args.verbose,
            headroom_override=args.headroom_override,
        )

        if not launcher.initialize():
            return 1

        if args.command == "launch":
            if args.target == "yantra":
                return launcher.start_interactive_session()

    except KeyboardInterrupt:
        print("\n⏹️  Interrupted", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
