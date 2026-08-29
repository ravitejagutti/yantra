"""Hook management for Yantra sessions.

Manages Claude hooks (PreToolUse, PostToolUse) for:
- Safety gates (block dangerous operations)
- Context injection (add machine state to results)

Handles registration and configuration of hooks from JSON files.
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional


class HookManager:
    """Manages Claude session hooks.

    Supports:
    - PreToolUse hooks (block/approve tools before execution)
    - PostToolUse hooks (enhance results with context)

    Hooks are defined in hooks.json and reference JavaScript implementations.
    """

    HOOK_TYPES = ["PreToolUse", "PostToolUse"]

    def __init__(self, config_dir: Optional[Path] = None, verbose: bool = False) -> None:
        """Initialize hook manager.

        Args:
            config_dir: Directory containing hooks.json
            verbose: If True, print hook loading details
        """
        self.config_dir = config_dir or Path.cwd()
        self.verbose = verbose
        self.hooks: Dict[str, Any] = {}
        self.enabled_hooks: List[str] = []

    def load_hooks(self) -> None:
        """Load hooks configuration from hooks.json.

        Reads hooks.json and identifies enabled hooks for later use.

        Raises:
            FileNotFoundError: If hooks.json not found
            ValueError: If hooks.json contains invalid data
        """
        hooks_file = self.config_dir / "hooks.json"

        if not hooks_file.exists():
            if self.verbose:
                print("⚠  hooks.json not found (hooks disabled)")
            return

        try:
            with open(hooks_file, "r") as f:
                config = json.load(f)

            self.hooks = config.get("hooks", [])
            self._identify_enabled_hooks()

            if self.verbose:
                print(f"✓ Hooks loaded ({len(self.enabled_hooks)} enabled)")

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in hooks.json: {e}")
        except Exception as e:
            raise ValueError(f"Failed to load hooks.json: {e}")

    def _identify_enabled_hooks(self) -> None:
        """Identify which hooks are enabled in configuration."""
        self.enabled_hooks = [
            hook.get("id") for hook in self.hooks if hook.get("enabled", False)
        ]

    def get_enabled_hooks(self) -> List[str]:
        """Get list of enabled hook IDs.

        Returns:
            List of enabled hook identifiers
        """
        return self.enabled_hooks.copy()

    def get_hook_config(self, hook_id: str) -> Optional[Dict[str, Any]]:
        """Get configuration for specific hook.

        Args:
            hook_id: Hook identifier

        Returns:
            Hook configuration dict or None if not found
        """
        for hook in self.hooks:
            if hook.get("id") == hook_id:
                return hook.copy()

        return None

    def get_hooks_by_type(self, hook_type: str) -> List[Dict[str, Any]]:
        """Get all hooks of a specific type.

        Args:
            hook_type: Hook type (PreToolUse or PostToolUse)

        Returns:
            List of matching hook configurations
        """
        return [
            hook
            for hook in self.hooks
            if hook.get("type") == hook_type and hook.get("enabled", False)
        ]

    def validate_hooks(self) -> bool:
        """Validate hook configuration and implementations.

        Checks:
        - Hook JSON structure is valid
        - Handler files exist
        - Hook types are recognized

        Returns:
            True if all hooks are valid, False otherwise
        """
        if not self.hooks:
            return True

        issues = []

        for hook in self.hooks:
            # Check required fields
            hook_id = hook.get("id")
            hook_type = hook.get("type")
            handler = hook.get("handler")
            enabled = hook.get("enabled", False)

            if not hook_id:
                issues.append("Hook missing 'id' field")
                continue

            if not hook_type or hook_type not in self.HOOK_TYPES:
                issues.append(f"Hook '{hook_id}': invalid type '{hook_type}'")

            # Check handler file exists if enabled
            if enabled and handler:
                handler_path = self.config_dir / handler
                if not handler_path.exists():
                    issues.append(
                        f"Hook '{hook_id}': handler file not found at {handler}"
                    )

        if issues:
            if self.verbose:
                print("⚠  Hook validation issues:")
                for issue in issues:
                    print(f"  - {issue}")
            return False

        return True

    def get_safety_gates(self) -> List[Dict[str, Any]]:
        """Get all enabled PreToolUse safety gate hooks.

        Returns:
            List of safety gate hook configurations
        """
        return self.get_hooks_by_type("PreToolUse")

    def get_context_injectors(self) -> List[Dict[str, Any]]:
        """Get all enabled PostToolUse context injection hooks.

        Returns:
            List of context injector hook configurations
        """
        return self.get_hooks_by_type("PostToolUse")

    def format_for_claude_config(self) -> Dict[str, Any]:
        """Format hooks for Claude configuration.

        Converts Yantra hook format to Claude hook format.

        Returns:
            Dictionary ready for inclusion in Claude config
        """
        claude_hooks = {}

        for hook in self.hooks:
            if not hook.get("enabled"):
                continue

            hook_id = hook.get("id")
            hook_type = hook.get("type")
            handler = hook.get("handler")

            if not all([hook_id, hook_type, handler]):
                continue

            if hook_type not in claude_hooks:
                claude_hooks[hook_type] = []

            claude_hooks[hook_type].append(
                {
                    "id": hook_id,
                    "description": hook.get("description", ""),
                    "handler": str(self.config_dir / handler),
                }
            )

        return claude_hooks

    def print_summary(self) -> None:
        """Print summary of loaded hooks."""
        if not self.hooks:
            print("No hooks configured")
            return

        enabled = sum(1 for h in self.hooks if h.get("enabled", False))
        disabled = len(self.hooks) - enabled

        print(f"\nHooks Summary:")
        print(f"  Enabled:  {enabled}")
        print(f"  Disabled: {disabled}")
        print()

        # Show enabled hooks by type
        for hook_type in self.HOOK_TYPES:
            hooks = self.get_hooks_by_type(hook_type)
            if hooks:
                print(f"  {hook_type}:")
                for hook in hooks:
                    print(f"    • {hook.get('id')}: {hook.get('description', '')}")
