"""Tests for launcher.validator - Headroom resolution and EnvironmentValidator.

Real tools (Node, Claude, Headroom) are mocked - these test the *logic*
(priority order, fallback behavior, error handling), not whether your
machine happens to have everything installed.
"""

import subprocess
import unittest
from unittest.mock import patch, MagicMock

from launcher import validator


class TestFindHeadroomExecutable(unittest.TestCase):
    def test_prefers_dedicated_venv_over_path(self):
        """The venv install (see HEADROOM_VENV_DIR) must win even if a
        stale/different headroom happens to also be on PATH - this is the
        exact scenario that caused a broken Headroom install to keep being
        picked up after the real Windows MAX_PATH fix was in place."""
        with patch.object(validator, "_headroom_venv_executable", return_value="/venv/headroom"), \
             patch("shutil.which", return_value="/some/other/headroom"):
            self.assertEqual(validator.find_headroom_executable(), "/venv/headroom")

    def test_falls_back_to_path_when_venv_missing(self):
        with patch.object(validator, "_headroom_venv_executable", return_value=None), \
             patch("shutil.which", return_value="/usr/local/bin/headroom"):
            self.assertEqual(validator.find_headroom_executable(), "/usr/local/bin/headroom")

    def test_returns_none_when_nothing_found(self):
        with patch.object(validator, "_headroom_venv_executable", return_value=None), \
             patch("shutil.which", return_value=None), \
             patch("pathlib.Path.exists", return_value=False):
            self.assertIsNone(validator.find_headroom_executable())


class TestGetHeadroomVenvPython(unittest.TestCase):
    def test_windows_path_uses_scripts_dir(self):
        with patch.object(validator.sys, "platform", "win32"):
            result = validator.get_headroom_venv_python()
            self.assertTrue(str(result).endswith(("Scripts\\python.exe", "Scripts/python.exe")))

    def test_posix_path_uses_bin_dir(self):
        # Use .parts (not string endswith) so this is correct regardless of
        # which OS actually runs the test - pathlib joins with segments,
        # not a hardcoded separator, so patching sys.platform changes which
        # branch runs but not which separator the *test process's own* OS
        # would stringify the result with.
        with patch.object(validator.sys, "platform", "linux"):
            result = validator.get_headroom_venv_python()
            self.assertEqual(result.parts[-2:], ("bin", "python"))


class TestEnvironmentValidatorNode(unittest.TestCase):
    def setUp(self):
        self.v = validator.EnvironmentValidator(verbose=False)

    def test_node_not_found_is_an_issue(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            self.v._check_node()
        self.assertTrue(any("Node.js not found" in i for i in self.v.issues))

    def test_node_too_old_is_an_issue(self):
        result = MagicMock(returncode=0, stdout="v16.2.0\n")
        with patch("subprocess.run", return_value=result):
            self.v._check_node()
        self.assertTrue(any("too old" in i for i in self.v.issues))

    def test_node_new_enough_is_not_an_issue(self):
        result = MagicMock(returncode=0, stdout="v20.10.0\n")
        with patch("subprocess.run", return_value=result):
            self.v._check_node()
        self.assertEqual(self.v.issues, [])

    def test_node_timeout_is_an_issue(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="node", timeout=5)):
            self.v._check_node()
        self.assertTrue(any("timed out" in i for i in self.v.issues))


class TestEnvironmentValidatorClaudeCli(unittest.TestCase):
    def setUp(self):
        self.v = validator.EnvironmentValidator(verbose=False)

    def test_claude_not_on_path_is_an_issue(self):
        with patch("shutil.which", return_value=None):
            self.v._check_claude_cli()
        self.assertTrue(any("Claude CLI not found" in i for i in self.v.issues))

    def test_uses_resolved_path_not_bare_command(self):
        """Regression test for the Windows claude.cmd WinError 2 bug - must
        call subprocess.run with the *resolved* path, not the literal
        string "claude", since Windows can't exec a bare name that
        resolves to a .cmd shim without the extension."""
        result = MagicMock(returncode=0)
        with patch("shutil.which", return_value="C:\\npm\\claude.CMD"), \
             patch("subprocess.run", return_value=result) as mock_run:
            self.v._check_claude_cli()
        called_args = mock_run.call_args[0][0]
        self.assertEqual(called_args[0], "C:\\npm\\claude.CMD")
        self.assertNotEqual(called_args[0], "claude")


class TestEnvironmentValidatorHeadroom(unittest.TestCase):
    def setUp(self):
        self.v = validator.EnvironmentValidator(verbose=False)

    def test_missing_headroom_is_a_warning_not_an_issue(self):
        """Headroom is optional - its absence must never fail validate_all()."""
        with patch.object(validator, "find_headroom_executable", return_value=None):
            self.v._check_headroom()
        self.assertEqual(self.v.issues, [])
        self.assertTrue(any("Headroom not found" in w for w in self.v.warnings))

    def test_present_headroom_produces_no_warning(self):
        with patch.object(validator, "find_headroom_executable", return_value="/path/headroom"):
            self.v._check_headroom()
        self.assertEqual(self.v.warnings, [])


class TestValidateAllNeverBlocksOnHeadroom(unittest.TestCase):
    def test_validate_all_passes_with_only_headroom_missing(self):
        v = validator.EnvironmentValidator(verbose=False)
        node_result = MagicMock(returncode=0, stdout="v20.0.0\n")
        with patch("subprocess.run", return_value=node_result), \
             patch("shutil.which", return_value="/usr/bin/claude"), \
             patch.object(validator, "find_headroom_executable", return_value=None):
            self.assertTrue(v.validate_all())


if __name__ == "__main__":
    unittest.main()
