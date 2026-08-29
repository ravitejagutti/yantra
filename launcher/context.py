"""Context injection for Yantra sessions.

Injects machine state and environment context into Claude sessions:
- Git branch and status
- Working directory
- System information
- Environment variables (filtered for safety)
- Timestamp
"""

import os
import sys
import subprocess
import platform
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime


class ContextInjector:
    """Injects machine context into Yantra sessions.

    Gathers:
    - Git context (branch, status, repo root)
    - Working directory and filesystem state
    - System information (OS, Python version, etc.)
    - Safe environment variables
    - Timestamp
    """

    # Environment variables safe to expose
    SAFE_ENV_VARS = [
        "USER",
        "HOME",
        "SHELL",
        "LANG",
        "PATH",
        "PWD",
        "TMPDIR",
        "TERM",
    ]

    # Variables to NEVER expose
    BLOCKED_ENV_VARS = [
        "PASSWORD",
        "TOKEN",
        "SECRET",
        "API_KEY",
        "PRIVATE",
    ]

    def __init__(self, verbose: bool = False) -> None:
        """Initialize context injector.

        Args:
            verbose: If True, print debug info
        """
        self.verbose = verbose

    def inject_context(self) -> Dict[str, Any]:
        """Gather and return complete session context.

        Returns:
            Dictionary with all collected context
        """
        context = {
            "timestamp": self._get_timestamp(),
            "git": self._get_git_context(),
            "filesystem": self._get_filesystem_context(),
            "system": self._get_system_context(),
            "environment": self._get_safe_env_vars(),
        }

        if self.verbose:
            print(f"✓ Context injected ({len(context)} sections)")

        return context

    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format.

        Returns:
            ISO format timestamp string
        """
        return datetime.utcnow().isoformat() + "Z"

    def _get_git_context(self) -> Dict[str, Any]:
        """Get git repository context.

        Returns:
            Dictionary with git branch, status, dirty files count
        """
        context: Dict[str, Any] = {"available": False}

        try:
            # Check if in git repo
            result = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                capture_output=True,
                text=True,
                timeout=2,
            )

            if result.returncode != 0:
                return context

            # Get branch name
            try:
                branch = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                ).stdout.strip()
            except Exception:
                branch = "unknown"

            # Get status
            try:
                status = subprocess.run(
                    ["git", "status", "--porcelain"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                ).stdout

                modified_files = len(status.strip().split("\n")) if status.strip() else 0
            except Exception:
                modified_files = 0

            context = {
                "available": True,
                "branch": branch,
                "modified_files": modified_files,
                "dirty": modified_files > 0,
            }

        except subprocess.TimeoutExpired:
            context["error"] = "git check timed out"
        except Exception as e:
            if self.verbose:
                print(f"  Git context error: {e}")

        return context

    def _get_filesystem_context(self) -> Dict[str, Any]:
        """Get filesystem context.

        Returns:
            Dictionary with working directory and file count
        """
        context = {
            "working_directory": os.getcwd(),
        }

        try:
            # Count files in current directory
            files = [f for f in os.listdir(".") if os.path.isfile(f)]
            dirs = [d for d in os.listdir(".") if os.path.isdir(d)]

            context["files_in_cwd"] = len(files)
            context["dirs_in_cwd"] = len(dirs)

        except Exception as e:
            if self.verbose:
                print(f"  Filesystem context error: {e}")

        return context

    def _get_system_context(self) -> Dict[str, Any]:
        """Get system information context.

        Returns:
            Dictionary with OS, Python version, CPU info
        """
        return {
            "platform": sys.platform,
            "os": platform.system(),
            "python_version": sys.version.split()[0],
            "architecture": platform.machine(),
            "hostname": platform.node(),
        }

    def _get_safe_env_vars(self) -> Dict[str, str]:
        """Get safe environment variables.

        Filters to only include safe variables and excludes blocked ones.

        Returns:
            Dictionary of safe environment variables
        """
        safe_vars = {}

        for var_name in self.SAFE_ENV_VARS:
            # Check if it's a blocked variable
            if any(blocked in var_name.upper() for blocked in self.BLOCKED_ENV_VARS):
                continue

            value = os.getenv(var_name)
            if value:
                safe_vars[var_name] = value

        return safe_vars

    def format_context_for_prompt(self, context: Dict[str, Any]) -> str:
        """Format context as human-readable text for Claude.

        Args:
            context: Context dictionary from inject_context()

        Returns:
            Formatted string for inclusion in prompts
        """
        lines = ["# Context", ""]

        # Git context
        git = context.get("git", {})
        if git.get("available"):
            lines.append(f"**Git Branch:** `{git.get('branch', 'unknown')}`")
            if git.get("dirty"):
                lines.append(
                    f"**Git Status:** {git.get('modified_files', 0)} modified files"
                )
            lines.append("")

        # Filesystem
        fs = context.get("filesystem", {})
        if fs.get("working_directory"):
            lines.append(f"**Working Directory:** `{fs['working_directory']}`")
            lines.append("")

        # System info (brief)
        system = context.get("system", {})
        if system:
            lines.append(
                f"**System:** {system.get('os', 'unknown')} "
                f"({system.get('platform', 'unknown')})"
            )
            lines.append(f"**Python:** {system.get('python_version', 'unknown')}")
            lines.append("")

        return "\n".join(lines)
