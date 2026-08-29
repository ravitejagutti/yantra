"""Tests for launcher.session.SessionLauncher._build_launch_command().

This is the single most important piece of business logic in Yantra: it
decides whether Claude gets launched plain or Headroom-wrapped, and with
which flags. Every case here was manually verified at least once during
development (see README's Configuration/Troubleshooting sections for the
real-world bugs these guard against) - this file turns that manual
verification into a permanent regression suite.
"""

import unittest
from pathlib import Path
from unittest.mock import patch

from launcher.config import YantraConfig
from launcher.session import SessionLauncher


def make_launcher(headroom_override=None, headroom_config=None, verbose=False):
    """Build a SessionLauncher with a config already set, bypassing
    initialize() (which would need real Node/Claude/git on the machine)."""
    launcher = SessionLauncher(
        config_dir=Path("."), verbose=verbose, headroom_override=headroom_override
    )
    launcher.config = YantraConfig(
        headroom=headroom_config if headroom_config is not None else {"enabled": True, "args": []}
    )
    return launcher


class TestHeadroomEnabledPriority(unittest.TestCase):
    """Priority order: CLI override > config > default-enabled."""

    def test_config_enabled_true_wraps_with_headroom(self):
        launcher = make_launcher(headroom_config={"enabled": True, "args": []})
        with patch("launcher.session.find_headroom_executable", return_value="/bin/headroom"):
            cmd = launcher._build_launch_command()
        self.assertEqual(cmd[0], "/bin/headroom")
        self.assertIn("wrap", cmd)
        self.assertIn("claude", cmd)

    def test_config_enabled_false_launches_plain_claude(self):
        launcher = make_launcher(headroom_config={"enabled": False, "args": []})
        with patch("launcher.session.find_headroom_executable", return_value="/bin/headroom"), \
             patch("shutil.which", return_value="/bin/claude"):
            cmd = launcher._build_launch_command()
        self.assertEqual(cmd, ["/bin/claude"])

    def test_cli_override_true_wins_over_config_disabled(self):
        launcher = make_launcher(
            headroom_override=True, headroom_config={"enabled": False, "args": []}
        )
        with patch("launcher.session.find_headroom_executable", return_value="/bin/headroom"):
            cmd = launcher._build_launch_command()
        self.assertEqual(cmd[0], "/bin/headroom")

    def test_cli_override_false_wins_over_config_enabled(self):
        launcher = make_launcher(
            headroom_override=False, headroom_config={"enabled": True, "args": []}
        )
        with patch("launcher.session.find_headroom_executable", return_value="/bin/headroom"), \
             patch("shutil.which", return_value="/bin/claude"):
            cmd = launcher._build_launch_command()
        self.assertEqual(cmd, ["/bin/claude"])

    def test_no_config_at_all_defaults_to_enabled(self):
        """No yantra.config.json present -> config.headroom uses the
        dataclass default, which must be enabled=True."""
        launcher = SessionLauncher(config_dir=Path("."), verbose=False)
        launcher.config = YantraConfig()  # dataclass default: enabled=True
        with patch("launcher.session.find_headroom_executable", return_value="/bin/headroom"):
            cmd = launcher._build_launch_command()
        self.assertEqual(cmd[0], "/bin/headroom")


class TestHeadroomMissingFallsBackGracefully(unittest.TestCase):
    def test_enabled_but_not_installed_falls_back_to_claude(self):
        """Headroom enabled in config, but not actually installed - must
        never crash or block the launch, just fall back silently."""
        launcher = make_launcher(headroom_config={"enabled": True, "args": []})
        with patch("launcher.session.find_headroom_executable", return_value=None), \
             patch("shutil.which", return_value="/bin/claude"):
            cmd = launcher._build_launch_command()
        self.assertEqual(cmd, ["/bin/claude"])


class TestHeadroomArgsPassthrough(unittest.TestCase):
    def test_extra_args_are_appended_after_claude(self):
        launcher = make_launcher(headroom_config={"enabled": True, "args": ["--no-mcp"]})
        with patch("launcher.session.find_headroom_executable", return_value="/bin/headroom"):
            cmd = launcher._build_launch_command()
        self.assertEqual(cmd, ["/bin/headroom", "wrap", "claude", "--no-mcp"])

    def test_no_args_produces_plain_wrap_command(self):
        launcher = make_launcher(headroom_config={"enabled": True, "args": []})
        with patch("launcher.session.find_headroom_executable", return_value="/bin/headroom"):
            cmd = launcher._build_launch_command()
        self.assertEqual(cmd, ["/bin/headroom", "wrap", "claude"])


class TestClaudeCmdWindowsResolution(unittest.TestCase):
    def test_fallback_resolves_full_path_not_bare_claude(self):
        """Regression test for the Windows claude.cmd WinError 2 bug in the
        Headroom-fallback path specifically (see TestEnvironmentValidatorClaudeCli
        for the same fix in the validator's version-check path)."""
        launcher = make_launcher(headroom_config={"enabled": False, "args": []})
        with patch("shutil.which", return_value="C:\\npm\\claude.CMD"):
            cmd = launcher._build_launch_command()
        self.assertEqual(cmd, ["C:\\npm\\claude.CMD"])

    def test_fallback_still_returns_something_if_which_fails(self):
        """Even if shutil.which can't resolve it, don't crash - fall back
        to the bare command string so subprocess at least attempts it."""
        launcher = make_launcher(headroom_config={"enabled": False, "args": []})
        with patch("shutil.which", return_value=None):
            cmd = launcher._build_launch_command()
        self.assertEqual(cmd, ["claude"])


class TestBuildClaudeEnvironment(unittest.TestCase):
    def test_always_sets_headroom_rust_core_workaround(self):
        """Must always be set, even when Headroom isn't in play - it's a
        harmless no-op then, but required whenever Headroom IS wrapping,
        to work around Windows Smart App Control blocking Headroom's
        native extension (see README Troubleshooting)."""
        launcher = make_launcher()
        env = launcher._build_claude_environment()
        self.assertEqual(env["HEADROOM_REQUIRE_RUST_CORE"], "false")

    def test_custom_environment_from_config_is_included(self):
        launcher = make_launcher()
        launcher.config.environment = {"MY_VAR": "hello"}
        env = launcher._build_claude_environment()
        self.assertEqual(env["MY_VAR"], "hello")

    def test_no_config_still_returns_the_safety_env_var(self):
        launcher = SessionLauncher(config_dir=Path("."), verbose=False)
        launcher.config = None
        env = launcher._build_claude_environment()
        self.assertEqual(env["HEADROOM_REQUIRE_RUST_CORE"], "false")


if __name__ == "__main__":
    unittest.main()
