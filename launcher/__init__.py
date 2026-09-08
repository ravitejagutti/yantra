"""Yantra v1 launcher module."""

import json
from pathlib import Path

from .session import SessionLauncher
from .config import ConfigLoader
from .validator import EnvironmentValidator
from .context import ContextInjector
from .hooks import HookManager


def _read_version() -> str:
    """Read Yantra's version from its own bundled config/yantra.config.json.

    This always resolves to the config shipped next to this package -
    never a caller's `--config-dir` override - because __version__ names
    the installed code, not whichever config a run happens to load.
    Falls back to "unknown" rather than raising, so a missing/corrupt
    config file never breaks `import launcher`.
    """
    config_path = Path(__file__).resolve().parent.parent / "config" / "yantra.config.json"
    try:
        with open(config_path, "r") as f:
            return json.load(f)["environment"]["YANTRA_VERSION"]
    except (OSError, KeyError, json.JSONDecodeError):
        return "unknown"


__version__ = _read_version()
__all__ = [
    "SessionLauncher",
    "ConfigLoader",
    "EnvironmentValidator",
    "ContextInjector",
    "HookManager",
]
