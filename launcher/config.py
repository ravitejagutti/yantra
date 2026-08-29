"""Configuration loading for Yantra sessions.

Loads and manages Yantra configuration from:
- JSON config files (skills, hooks, system prompts)
- Environment variables
- .env files

Supports template substitution with environment variables.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class YantraConfig:
    """Yantra configuration container.

    Attributes:
        skills: Available skills configuration
        hooks: Hook definitions (safety gates, context injection)
        system_prompt_template: System prompt template with placeholders
        environment: Environment variables to pass to Claude
        headroom: Headroom token-optimization wrapper settings
            (enabled: bool, args: list of extra "headroom wrap claude" flags)
    """

    skills: Dict[str, Any] = field(default_factory=dict)
    hooks: Dict[str, Any] = field(default_factory=dict)
    system_prompt_template: str = ""
    environment: Dict[str, str] = field(default_factory=dict)
    headroom: Dict[str, Any] = field(default_factory=lambda: {"enabled": True, "args": []})


class ConfigLoader:
    """Loads and manages Yantra configuration.

    Searches for config files in standard locations:
    - Current directory
    - ~/.yantra/
    - Project root (if running as module)
    """

    DEFAULT_CONFIG_NAME = "yantra.config.json"
    DEFAULT_HOOKS_NAME = "hooks.json"
    DEFAULT_SYSTEM_PROMPT = "system-prompt.md"

    def __init__(self, config_dir: Optional[Path] = None, verbose: bool = False) -> None:
        """Initialize config loader.

        Args:
            config_dir: Directory to load configs from (default: current dir)
            verbose: If True, print config loading details
        """
        self.config_dir = config_dir or Path.cwd()
        self.verbose = verbose

    def load(self) -> YantraConfig:
        """Load complete Yantra configuration.

        Loads from:
        1. yantra.config.json (skills, hooks references)
        2. hooks.json (hook definitions)
        3. system-prompt.md (system prompt template)

        Returns:
            YantraConfig with all loaded configuration

        Raises:
            FileNotFoundError: If required config files not found
            ValueError: If config files contain invalid data
        """
        config = YantraConfig()

        # Load main config
        main_config = self._load_json(self.DEFAULT_CONFIG_NAME)
        if main_config:
            config.skills = main_config.get("skills", {})
            config.hooks = main_config.get("hooks", {})
            config.environment = main_config.get("environment", {})
            if "headroom" in main_config:
                config.headroom = {**config.headroom, **main_config["headroom"]}

        # Load hooks definition
        hooks_config = self._load_json(self.DEFAULT_HOOKS_NAME)
        if hooks_config:
            config.hooks.update(hooks_config)

        # Load system prompt
        system_prompt = self._load_text(self.DEFAULT_SYSTEM_PROMPT)
        if system_prompt:
            config.system_prompt_template = system_prompt

        if self.verbose:
            print(f"✓ Configuration loaded from {self.config_dir}")

        return config

    def _load_json(self, filename: str) -> Optional[Dict[str, Any]]:
        """Load JSON config file.

        Args:
            filename: Name of JSON file to load

        Returns:
            Parsed JSON data or None if file not found

        Raises:
            ValueError: If JSON is invalid
        """
        filepath = self.config_dir / filename

        if not filepath.exists():
            if self.verbose:
                print(f"  Config file not found: {filename} (optional)")
            return None

        try:
            with open(filepath, "r") as f:
                data = json.load(f)

            if self.verbose:
                print(f"  ✓ Loaded {filename}")

            return data

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {filename}: {e}")
        except Exception as e:
            raise ValueError(f"Failed to load {filename}: {e}")

    def _load_text(self, filename: str) -> Optional[str]:
        """Load text config file.

        Args:
            filename: Name of text file to load

        Returns:
            File contents or None if file not found
        """
        filepath = self.config_dir / filename

        if not filepath.exists():
            if self.verbose:
                print(f"  Config file not found: {filename} (optional)")
            return None

        try:
            content = filepath.read_text()

            if self.verbose:
                print(f"  ✓ Loaded {filename}")

            return content

        except Exception as e:
            raise ValueError(f"Failed to load {filename}: {e}")

    def substitute_environment(self, config: YantraConfig) -> None:
        """Substitute environment variables in configuration.

        Replaces ${VAR_NAME} with environment variable values.

        Args:
            config: Configuration to update in-place
        """
        # Substitute in system prompt
        if config.system_prompt_template:
            config.system_prompt_template = self._substitute_template(
                config.system_prompt_template
            )

        # Substitute in environment dict
        for key, value in config.environment.items():
            if isinstance(value, str):
                config.environment[key] = self._substitute_template(value)

    def _substitute_template(self, template: str) -> str:
        """Substitute ${VAR} placeholders with environment values.

        Args:
            template: Template string with ${VAR_NAME} placeholders

        Returns:
            Template with substitutions applied
        """
        result = template

        # Find all ${VAR_NAME} patterns
        import re

        pattern = r"\$\{([^}]+)\}"
        matches = re.findall(pattern, template)

        for var_name in matches:
            value = os.getenv(var_name, f"${{{var_name}}}")  # Keep if not found
            result = result.replace(f"${{{var_name}}}", value)

        return result

    @staticmethod
    def get_config_dir() -> Path:
        """Get default configuration directory.

        Searches in order:
        1. Current directory
        2. ~/.yantra/
        3. Script directory

        Returns:
            Path to configuration directory
        """
        # Try current directory
        if (Path.cwd() / "yantra.config.json").exists():
            return Path.cwd()

        # Try ~/.yantra/
        yantra_dir = Path.home() / ".yantra"
        if (yantra_dir / "yantra.config.json").exists():
            return yantra_dir

        # Default to current
        return Path.cwd()
