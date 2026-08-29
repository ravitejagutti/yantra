"""Environment validation for Yantra sessions.

Validates prerequisites before launching Claude:
- Node.js version (>= 20.0.0)
- Claude CLI installation
- Headroom (optional, for token optimization)
"""

import os
import sys
import subprocess
import shutil
from typing import Tuple, Dict, List, Optional
from pathlib import Path


class ValidationError(Exception):
    """Raised when environment validation fails."""

    pass


# On Windows, `yantra setup` installs Headroom into a dedicated venv at a
# short path rather than the ambient (usually Microsoft Store) Python's
# site-packages. Store Python's install path is ~124 characters before any
# package name is even appended - long enough that headroom-ai's own
# dependencies (litellm's deeply nested guardrail test fixtures) can exceed
# Windows' legacy 260-char MAX_PATH, silently corrupting the install (files
# like litellm's own __init__.py never get written) unless the system has
# long paths enabled - which Windows ships with disabled by default, and
# enabling it requires admin rights. A short venv sidesteps this without
# needing admin. macOS/Linux have no such path limit, so this is unused
# there - see run_setup() in yantra.py.
HEADROOM_VENV_DIR = Path.home() / ".yantra" / "venv"


def get_headroom_venv_python() -> Path:
    """Path to the Python executable inside Yantra's dedicated Headroom venv."""
    if sys.platform == "win32":
        return HEADROOM_VENV_DIR / "Scripts" / "python.exe"
    return HEADROOM_VENV_DIR / "bin" / "python"


def _headroom_venv_executable() -> Optional[str]:
    """Path to headroom.exe/headroom inside the dedicated venv, if it exists."""
    if sys.platform == "win32":
        candidate = HEADROOM_VENV_DIR / "Scripts" / "headroom.exe"
    else:
        candidate = HEADROOM_VENV_DIR / "bin" / "headroom"

    return str(candidate) if candidate.exists() else None


def find_headroom_executable() -> Optional[str]:
    """Locate the Headroom CLI executable (https://github.com/headroomlabs-ai/headroom).

    Checks Yantra's dedicated venv first (see HEADROOM_VENV_DIR) - that's
    where `yantra setup` installs it on Windows, specifically to avoid a
    corrupted install from the Windows MAX_PATH issue. Then falls back to
    PATH via shutil.which(), then to other known user-install script
    directories, since a `pip install` can land Headroom in a folder that
    isn't on PATH yet until a new shell picks up the updated PATH.

    Returns:
        Full path to the headroom executable, or None if not found.
    """
    venv_headroom = _headroom_venv_executable()
    if venv_headroom:
        return venv_headroom

    path = shutil.which("headroom")
    if path:
        return path

    candidates = []

    if sys.platform == "win32":
        exe_name = "headroom.exe"

        appdata = os.environ.get("APPDATA", "")
        if appdata:
            candidates.extend(Path(appdata).glob(f"Python/Python3*/Scripts/{exe_name}"))

        localappdata = os.environ.get("LOCALAPPDATA", "")
        if localappdata:
            # Microsoft Store Python user-install location
            candidates.extend(
                Path(localappdata).glob(
                    f"Packages/PythonSoftwareFoundation.Python.*/LocalCache/"
                    f"local-packages/Python*/Scripts/{exe_name}"
                )
            )
    else:
        exe_name = "headroom"
        candidates.append(Path.home() / ".local" / "bin" / exe_name)

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    return None


class EnvironmentValidator:
    """Validates system prerequisites for Yantra sessions.

    Checks:
    - Node.js installed and version >= 20.0.0
    - Claude CLI installed
    - Headroom installed (optional, non-fatal if missing)
    """

    MIN_NODE_VERSION = 20

    def __init__(self, verbose: bool = False) -> None:
        """Initialize validator.

        Args:
            verbose: If True, print detailed validation info
        """
        self.verbose = verbose
        self.issues: List[str] = []
        self.warnings: List[str] = []

    def validate_all(self) -> bool:
        """Run all validation checks.

        Returns:
            True if all critical checks pass, False otherwise
        """
        self.issues.clear()
        self.warnings.clear()

        # Run checks
        self._check_node()
        self._check_claude_cli()
        self._check_headroom()

        if self.issues:
            self._print_issues()
            return False

        if self.warnings and self.verbose:
            self._print_warnings()

        return True

    def _check_node(self) -> None:
        """Verify Node.js is installed and version >= 20.0.0."""
        try:
            result = subprocess.run(
                ["node", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                self.issues.append("Node.js not found or failed to execute")
                return

            version_str = result.stdout.strip()  # e.g., "v20.10.0"

            try:
                major_version = int(version_str.split(".")[0].lstrip("v"))
            except (ValueError, IndexError):
                self.issues.append(f"Could not parse Node.js version: {version_str}")
                return

            if major_version < self.MIN_NODE_VERSION:
                self.issues.append(
                    f"Node.js version too old: {version_str} "
                    f"(need >= {self.MIN_NODE_VERSION}.0.0)"
                )
                return

            if self.verbose:
                print(f"✓ Node.js {version_str}")

        except FileNotFoundError:
            self.issues.append(
                "Node.js not found in PATH. "
                "Install from: https://nodejs.org/en/download/"
            )
        except subprocess.TimeoutExpired:
            self.issues.append("Node.js check timed out")
        except Exception as e:
            self.issues.append(f"Node.js check failed: {e}")

    def _check_claude_cli(self) -> None:
        """Verify Claude CLI is installed and accessible."""
        try:
            # First, check if claude exists in PATH using shutil.which()
            claude_path = shutil.which("claude")

            if not claude_path:
                self.issues.append(
                    "Claude CLI not found in PATH. "
                    "Install from: https://github.com/anthropics/claude-code"
                )
                return

            # Try to get version to verify it works. Use the resolved path,
            # not the bare "claude" - on Windows, npm installs Claude CLI as
            # claude.cmd, which subprocess can't execute without the .cmd
            # extension (WinError 2), even though shutil.which() finds it.
            result = subprocess.run(
                [claude_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                self.warnings.append(
                    "Claude CLI may not be properly configured. "
                    "Run 'claude --version' to verify installation."
                )
                return

            if self.verbose:
                print(f"✓ Claude CLI installed at {claude_path}")

        except subprocess.TimeoutExpired:
            self.warnings.append("Claude CLI check timed out")
        except Exception as e:
            self.warnings.append(f"Claude CLI check failed: {e}")

    def _check_headroom(self) -> None:
        """Check for Headroom (optional token-optimization wrapper).

        Non-fatal: Headroom cuts token consumption by proxying Claude's API
        traffic, but Yantra falls back to launching Claude directly if it's
        not installed, so a missing Headroom never blocks a session.
        """
        headroom_path = find_headroom_executable()

        if not headroom_path:
            self.warnings.append(
                "Headroom not found — Claude will launch without token "
                'optimization. Install with: pip install "headroom-ai[all]"'
            )
            return

        if self.verbose:
            print(f"✓ Headroom installed at {headroom_path}")

    def _print_issues(self) -> None:
        """Print validation issues (errors) to stderr."""
        print("❌ Validation Failed\n", file=sys.stderr)

        for issue in self.issues:
            print(f"  • {issue}", file=sys.stderr)

        print(f"\n💡 Fix the issues above and try again.\n", file=sys.stderr)

    def _print_warnings(self) -> None:
        """Print validation warnings to stdout."""
        print("⚠️  Warnings:\n")

        for warning in self.warnings:
            print(f"  • {warning}")

        print()

    def get_issues(self) -> List[str]:
        """Get list of validation issues.

        Returns:
            List of error messages
        """
        return self.issues.copy()

    def get_warnings(self) -> List[str]:
        """Get list of validation warnings.

        Returns:
            List of warning messages
        """
        return self.warnings.copy()
