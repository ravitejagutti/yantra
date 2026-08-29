"""Main session launcher for Yantra.

Orchestrates all components (config, validation, context, hooks)
to initialize and launch an enhanced Claude session.
"""

import os
import sys
import shutil
import subprocess
import webbrowser
from pathlib import Path
from typing import Optional, Dict, Any, List

from .config import ConfigLoader, YantraConfig
from .validator import EnvironmentValidator, ValidationError, find_headroom_executable
from .context import ContextInjector
from .hooks import HookManager


class SessionLauncher:
    """Launches enhanced Claude sessions with Yantra context.

    Orchestration flow:
    1. Load configuration
    2. Validate environment prerequisites
    3. Inject machine context
    4. Apply hooks (safety gates, context injection)
    5. Launch Claude with enhanced system prompt
    """

    def __init__(
        self,
        config_dir: Optional[Path] = None,
        verbose: bool = False,
        headroom_override: Optional[bool] = None,
    ) -> None:
        """Initialize session launcher.

        Args:
            config_dir: Directory containing Yantra config files
            verbose: If True, print detailed initialization info
            headroom_override: Force Headroom on (True) or off (False) for
                this run, overriding yantra.config.json's headroom.enabled.
                None (default) means "use the config value".
        """
        self.config_dir = config_dir or Path.cwd()
        self.verbose = verbose
        self.headroom_override = headroom_override

        # Initialize components
        self.config_loader = ConfigLoader(self.config_dir, verbose=verbose)
        self.validator = EnvironmentValidator(verbose=verbose)
        self.context_injector = ContextInjector(verbose=verbose)
        self.hook_manager = HookManager(self.config_dir, verbose=verbose)

        self.config: Optional[YantraConfig] = None
        self.context: Dict[str, Any] = {}

    def initialize(self) -> bool:
        """Initialize Yantra session.

        Performs:
        1. Config loading
        2. Environment validation
        3. Context injection setup
        4. Hook loading

        Returns:
            True if initialization successful, False otherwise
        """
        try:
            # Step 1: Load configuration
            if self.verbose:
                print("1️⃣  Loading configuration...")

            self.config = self.config_loader.load()
            self.config_loader.substitute_environment(self.config)

            # Step 2: Validate environment
            if self.verbose:
                print("2️⃣  Validating environment...")

            if not self.validator.validate_all():
                for issue in self.validator.get_issues():
                    print(f"❌ {issue}", file=sys.stderr)
                return False

            # Step 3: Inject context
            if self.verbose:
                print("3️⃣  Injecting machine context...")

            self.context = self.context_injector.inject_context()

            # Step 4: Load hooks
            if self.verbose:
                print("4️⃣  Loading hooks...")

            self.hook_manager.load_hooks()
            if not self.hook_manager.validate_hooks():
                if self.verbose:
                    print("⚠  Hook validation issues (continuing)")

            if self.verbose:
                print("\n✅ Initialization complete\n")

            return True

        except ValidationError as e:
            print(f"❌ Validation error: {e}", file=sys.stderr)
            return False
        except Exception as e:
            print(f"❌ Initialization failed: {e}", file=sys.stderr)
            if self.verbose:
                import traceback

                traceback.print_exc()
            return False

    def start_session(self) -> bool:
        """Prepare Claude session (authentication handled by Claude CLI).

        Claude CLI will handle authentication automatically if needed.

        Returns:
            True if ready to launch, False otherwise
        """
        if self.verbose:
            print("✓ Ready to launch Claude session")
            print("  (Claude CLI will handle authentication if needed)\n")
        return True

    def build_system_prompt(self) -> str:
        """Build complete system prompt with context.

        Returns:
            Complete system prompt for Claude session
        """
        if not self.config:
            return ""

        # Start with base template
        prompt = self.config.system_prompt_template

        # Add context section
        context_text = self.context_injector.format_context_for_prompt(self.context)
        prompt += "\n\n" + context_text

        # Add skills section if available
        if self.config.skills:
            prompt += "\n\n# Available Skills\n"
            for skill_id, skill_config in self.config.skills.items():
                description = skill_config.get("description", "")
                prompt += f"- **{skill_id}**: {description}\n"

        return prompt

    def start_interactive_session(self) -> int:
        """Start an interactive Claude session with Yantra enhancements.

        Launches Claude in interactive mode. Authentication is handled by Claude CLI.

        Returns:
            Exit code from Claude CLI
        """
        if not self.config:
            print("❌ Session not initialized", file=sys.stderr)
            return 1

        # Step 1: Prepare session
        if not self.start_session():
            print("❌ Failed to prepare session", file=sys.stderr)
            return 1

        # Step 2: Build environment for Claude
        claude_env = self._build_claude_environment()

        # Step 3: Show session info
        if self.verbose:
            print("\n📋 Session Information:")
            self.print_session_info()

        try:
            if self.verbose:
                print(f"🚀 Launching enhanced Claude session...\n")
            else:
                print("🚀 Launching Claude...\n")

            # Launch Claude CLI in interactive mode
            # This gives the user a full interactive Claude terminal
            cmd = self._build_launch_command()

            result = subprocess.run(
                cmd,
                env={**os.environ, **claude_env},
            )

            return result.returncode

        except FileNotFoundError:
            print("❌ Claude CLI not found", file=sys.stderr)
            print("Install from: https://github.com/anthropics/claude-code", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"❌ Failed to launch Claude: {e}", file=sys.stderr)
            return 1

    def _build_launch_command(self) -> List[str]:
        """Build the command used to launch Claude.

        Wraps Claude with Headroom (https://github.com/headroomlabs-ai/headroom)
        when it's installed and enabled, so API traffic is proxied through
        Headroom's compression pipeline to cut token consumption. Falls back
        to launching Claude directly — silently and without failing the
        session — if Headroom isn't installed or is disabled, so a missing
        Headroom never blocks `launch yantra`.

        Whether Headroom is enabled is decided by, in priority order:
        1. self.headroom_override (--headroom / --no-headroom on the CLI)
        2. config.headroom.enabled (yantra.config.json)
        3. Default: enabled

        Returns:
            Command list ready for subprocess.run()
        """
        headroom_cfg = (self.config.headroom if self.config else {}) or {}

        if self.headroom_override is not None:
            enabled = self.headroom_override
        else:
            enabled = headroom_cfg.get("enabled", True)

        if enabled:
            headroom_path = find_headroom_executable()

            if headroom_path:
                extra_args = headroom_cfg.get("args", [])
                print("🧠 Headroom enabled — optimizing token usage\n")
                return [headroom_path, "wrap", "claude", *extra_args]

            if self.verbose or self.headroom_override is True:
                print(
                    "⚠  Headroom not found — launching Claude directly "
                    "(no token optimization). Run: yantra setup\n"
                )
        elif self.verbose:
            print("ℹ  Headroom disabled for this run — launching Claude directly\n")

        # Resolve the full path, not the bare "claude" - on Windows, npm
        # installs Claude CLI as claude.cmd, which subprocess can't execute
        # without the .cmd extension (WinError 2), even though the command
        # is genuinely on PATH.
        return [shutil.which("claude") or "claude"]

    def _build_claude_environment(self) -> Dict[str, str]:
        """Build environment variables for the Claude subprocess."""
        env: Dict[str, str] = {}

        # Headroom's proxy imports a native Rust extension (_core) at
        # startup. On Windows machines with Smart App Control enforced (the
        # Windows 11 default), that unsigned binary can get blocked outright
        # ("An Application Control policy has blocked this file"),
        # crashing the proxy before Claude even launches. This env var
        # (documented in Headroom's own troubleshooting guide) makes that
        # failure non-fatal instead. Harmless no-op when Headroom isn't
        # actually in the launch command, so it's always safe to set.
        env["HEADROOM_REQUIRE_RUST_CORE"] = "false"

        if self.config:
            env.update(self.config.environment)

        return env

    def print_session_info(self) -> None:
        """Print session initialization information."""
        if not self.config:
            print("❌ Session not initialized")
            return

        print("\n📋 Yantra Session Information")
        print("=" * 50)

        # Config info
        print("\n✅ Configuration")
        print(f"  Skills: {len(self.config.skills)} available")
        print(f"  Hooks: {len(self.hook_manager.enabled_hooks)} enabled")

        # Context info
        git = self.context.get("git", {})
        print("\n📍 Context")
        if git.get("available"):
            print(f"  Git Branch: {git.get('branch')}")
            if git.get("dirty"):
                print(f"  Git Status: {git.get('modified_files')} modified")
        else:
            print("  Git: Not in repository")

        fs = self.context.get("filesystem", {})
        print(f"  Working Dir: {fs.get('working_directory')}")

        # System info
        system = self.context.get("system", {})
        print(f"  OS: {system.get('os')} ({system.get('platform')})")
        print(f"  Python: {system.get('python_version')}")

        # Hooks info
        self.hook_manager.print_summary()

        print("=" * 50 + "\n")
