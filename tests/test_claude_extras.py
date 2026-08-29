"""Tests for launcher.claude_extras (`yantra install` / `yantra uninstall`).

These tests NEVER touch the real ~/.claude/ - every test redirects
CLAUDE_SETTINGS_PATH and SKILL_INSTALL_PATH to an isolated temp directory
first. install()/uninstall() mutate a real user's global Claude Code
config, so getting the merge/idempotency/non-destructiveness logic right
here matters more than almost anything else in this codebase.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from launcher import claude_extras as ce

# A fake hook script path used across the merge/remove tests below. Must be
# a real Path object (not a hardcoded POSIX-style string) so str(FAKE_HOOK_PATH)
# matches whatever separator convention _is_yantra_handler() computes on
# the OS actually running the tests - a plain "/x/safety_gates.js" string
# literal would silently never match on Windows, where Path normalizes it
# to "\\x\\safety_gates.js".
FAKE_HOOK_PATH = Path("/x/safety_gates.js")


class ClaudeExtrasTestCase(unittest.TestCase):
    """Base class: redirects every path claude_extras writes to, to an
    isolated temp directory, and restores the real paths afterward."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        fake_home = Path(self.tmpdir.name)

        self._orig_settings_path = ce.CLAUDE_SETTINGS_PATH
        self._orig_skill_path = ce.SKILL_INSTALL_PATH

        ce.CLAUDE_SETTINGS_PATH = fake_home / "settings.json"
        ce.SKILL_INSTALL_PATH = fake_home / "skills" / "context-analysis" / "SKILL.md"

    def tearDown(self):
        ce.CLAUDE_SETTINGS_PATH = self._orig_settings_path
        ce.SKILL_INSTALL_PATH = self._orig_skill_path
        self.tmpdir.cleanup()


class TestLoadSettings(ClaudeExtrasTestCase):
    def test_missing_file_returns_empty_dict(self):
        self.assertEqual(ce._load_settings(), {})

    def test_invalid_json_raises_value_error_rather_than_overwriting(self):
        ce.CLAUDE_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        ce.CLAUDE_SETTINGS_PATH.write_text("{ not valid json")
        with self.assertRaises(ValueError):
            ce._load_settings()


class TestMergeHook(unittest.TestCase):
    def test_adds_new_matcher_group_when_none_exists(self):
        settings = {}
        ce._merge_hook(settings, "Bash", {"type": "command", "command": "node", "args": ["/x/safety_gates.js"]})
        self.assertEqual(len(settings["hooks"]["PreToolUse"]), 1)
        self.assertEqual(settings["hooks"]["PreToolUse"][0]["matcher"], "Bash")

    def test_appends_to_existing_matcher_group_without_touching_other_hooks(self):
        settings = {
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo", "args": ["unrelated"]}]}
                ]
            }
        }
        with patch.object(ce, "HOOK_SCRIPT_PATH", FAKE_HOOK_PATH):
            ce._merge_hook(settings, "Bash", {"type": "command", "command": "node", "args": [str(FAKE_HOOK_PATH)]})
        hooks = settings["hooks"]["PreToolUse"][0]["hooks"]
        self.assertEqual(len(hooks), 2)
        self.assertTrue(any(h["args"] == ["unrelated"] for h in hooks))

    def test_reinstall_replaces_stale_entry_instead_of_duplicating(self):
        """The core idempotency guarantee: running install twice must not
        produce two copies of Yantra's own hook."""
        with patch.object(ce, "HOOK_SCRIPT_PATH", FAKE_HOOK_PATH):
            settings = {}
            ce._merge_hook(settings, "Bash", {"type": "command", "command": "node_old", "args": [str(FAKE_HOOK_PATH)]})
            ce._merge_hook(settings, "Bash", {"type": "command", "command": "node_new", "args": [str(FAKE_HOOK_PATH)]})
            hooks = settings["hooks"]["PreToolUse"][0]["hooks"]
        self.assertEqual(len(hooks), 1)
        self.assertEqual(hooks[0]["command"], "node_new")


class TestRemoveHook(unittest.TestCase):
    def test_removes_only_yantras_own_entry(self):
        with patch.object(ce, "HOOK_SCRIPT_PATH", FAKE_HOOK_PATH):
            settings = {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {"type": "command", "command": "echo", "args": ["unrelated"]},
                                {"type": "command", "command": "node", "args": [str(FAKE_HOOK_PATH)]},
                            ],
                        }
                    ]
                }
            }
            removed = ce._remove_hook(settings)
        self.assertTrue(removed)
        remaining = settings["hooks"]["PreToolUse"][0]["hooks"]
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["args"], ["unrelated"])

    def test_drops_now_empty_matcher_group(self):
        with patch.object(ce, "HOOK_SCRIPT_PATH", FAKE_HOOK_PATH):
            settings = {
                "hooks": {
                    "PreToolUse": [
                        {"matcher": "Bash", "hooks": [{"type": "command", "command": "node", "args": [str(FAKE_HOOK_PATH)]}]}
                    ]
                }
            }
            ce._remove_hook(settings)
        self.assertEqual(settings["hooks"]["PreToolUse"], [])

    def test_nothing_to_remove_returns_false(self):
        self.assertFalse(ce._remove_hook({}))


class TestInstallUninstallEndToEnd(ClaudeExtrasTestCase):
    """Full install()/uninstall() cycle against the isolated fake home."""

    def setUp(self):
        super().setUp()
        self.node_patch = patch.object(ce, "find_node_executable", return_value="/usr/bin/node")
        self.node_patch.start()

    def tearDown(self):
        self.node_patch.stop()
        super().tearDown()

    def test_install_fails_cleanly_without_node(self):
        with patch.object(ce, "find_node_executable", return_value=None):
            self.assertEqual(ce.install(), 1)
        self.assertFalse(ce.CLAUDE_SETTINGS_PATH.exists())

    def test_install_creates_settings_and_skill_file(self):
        rc = ce.install()
        self.assertEqual(rc, 0)
        self.assertTrue(ce.CLAUDE_SETTINGS_PATH.exists())
        self.assertTrue(ce.SKILL_INSTALL_PATH.exists())

    def test_install_preserves_unrelated_existing_settings(self):
        ce.CLAUDE_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        ce.CLAUDE_SETTINGS_PATH.write_text(json.dumps({
            "hooks": {"PreToolUse": [{"matcher": "Write", "hooks": [{"type": "command", "command": "echo"}]}]},
            "someUnrelatedSetting": True,
        }))
        ce.install()
        data = json.loads(ce.CLAUDE_SETTINGS_PATH.read_text())
        self.assertTrue(data["someUnrelatedSetting"])
        self.assertTrue(any(g["matcher"] == "Write" for g in data["hooks"]["PreToolUse"]))

    def test_install_twice_does_not_duplicate(self):
        ce.install()
        ce.install()
        data = json.loads(ce.CLAUDE_SETTINGS_PATH.read_text())
        bash_group = next(g for g in data["hooks"]["PreToolUse"] if g["matcher"] == "Bash")
        self.assertEqual(len(bash_group["hooks"]), 1)

    def test_uninstall_removes_exactly_what_install_added(self):
        ce.install()
        rc = ce.uninstall()
        self.assertEqual(rc, 0)
        self.assertFalse(ce.SKILL_INSTALL_PATH.exists())
        data = json.loads(ce.CLAUDE_SETTINGS_PATH.read_text())
        self.assertEqual(data["hooks"]["PreToolUse"], [])

    def test_uninstall_without_prior_install_is_safe(self):
        rc = ce.uninstall()
        self.assertEqual(rc, 0)

    def test_uninstall_preserves_unrelated_settings(self):
        ce.CLAUDE_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        ce.CLAUDE_SETTINGS_PATH.write_text(json.dumps({
            "hooks": {"PreToolUse": [{"matcher": "Write", "hooks": [{"type": "command", "command": "echo"}]}]},
        }))
        ce.install()
        ce.uninstall()
        data = json.loads(ce.CLAUDE_SETTINGS_PATH.read_text())
        self.assertTrue(any(g["matcher"] == "Write" for g in data["hooks"]["PreToolUse"]))


if __name__ == "__main__":
    unittest.main()
