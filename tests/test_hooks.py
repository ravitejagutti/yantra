"""Tests for launcher.hooks.HookManager.

Loads hooks.json for the console summary/validation shown at startup - see
README's "Startup Flow" for why this does NOT register anything with
Claude Code itself (that's launcher.claude_extras / `yantra install`).
"""

import json
import tempfile
import unittest
from pathlib import Path

from launcher.hooks import HookManager


class TestLoadHooks(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.config_dir = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _write_hooks_json(self, hooks):
        (self.config_dir / "hooks.json").write_text(json.dumps({"hooks": hooks}))

    def test_missing_hooks_json_is_not_an_error(self):
        manager = HookManager(self.config_dir)
        manager.load_hooks()  # should not raise
        self.assertEqual(manager.hooks, {})
        self.assertEqual(manager.enabled_hooks, [])

    def test_enabled_hooks_are_identified(self):
        self._write_hooks_json([
            {"id": "safety_gates", "type": "PreToolUse", "enabled": True},
            {"id": "disabled_one", "type": "PreToolUse", "enabled": False},
        ])
        manager = HookManager(self.config_dir)
        manager.load_hooks()
        self.assertEqual(manager.get_enabled_hooks(), ["safety_gates"])

    def test_invalid_json_raises_value_error(self):
        (self.config_dir / "hooks.json").write_text("{ broken")
        manager = HookManager(self.config_dir)
        with self.assertRaises(ValueError):
            manager.load_hooks()


class TestGetHookConfig(unittest.TestCase):
    def setUp(self):
        self.manager = HookManager(Path("."))
        self.manager.hooks = [
            {"id": "safety_gates", "type": "PreToolUse", "enabled": True, "description": "blocks stuff"},
        ]

    def test_finds_existing_hook_by_id(self):
        config = self.manager.get_hook_config("safety_gates")
        self.assertEqual(config["description"], "blocks stuff")

    def test_returns_none_for_unknown_id(self):
        self.assertIsNone(self.manager.get_hook_config("nonexistent"))

    def test_returned_config_is_a_copy_not_a_reference(self):
        config = self.manager.get_hook_config("safety_gates")
        config["description"] = "mutated"
        self.assertEqual(self.manager.hooks[0]["description"], "blocks stuff")


class TestGetHooksByType(unittest.TestCase):
    def setUp(self):
        self.manager = HookManager(Path("."))
        self.manager.hooks = [
            {"id": "a", "type": "PreToolUse", "enabled": True},
            {"id": "b", "type": "PreToolUse", "enabled": False},  # disabled, excluded
            {"id": "c", "type": "PostToolUse", "enabled": True},
        ]

    def test_only_enabled_hooks_of_matching_type_returned(self):
        result = self.manager.get_hooks_by_type("PreToolUse")
        self.assertEqual([h["id"] for h in result], ["a"])

    def test_safety_gates_helper_matches_pretooluse(self):
        result = self.manager.get_safety_gates()
        self.assertEqual([h["id"] for h in result], ["a"])

    def test_context_injectors_helper_matches_posttooluse(self):
        result = self.manager.get_context_injectors()
        self.assertEqual([h["id"] for h in result], ["c"])


class TestValidateHooks(unittest.TestCase):
    def test_no_hooks_is_valid(self):
        manager = HookManager(Path("."))
        manager.hooks = []
        self.assertTrue(manager.validate_hooks())

    def test_missing_id_is_invalid(self):
        manager = HookManager(Path("."))
        manager.hooks = [{"type": "PreToolUse", "enabled": True}]
        self.assertFalse(manager.validate_hooks())

    def test_unrecognized_type_is_invalid(self):
        manager = HookManager(Path("."))
        manager.hooks = [{"id": "x", "type": "NotARealType", "enabled": True}]
        self.assertFalse(manager.validate_hooks())

    def test_enabled_hook_with_missing_handler_file_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = HookManager(Path(tmp))
            manager.hooks = [
                {"id": "x", "type": "PreToolUse", "enabled": True, "handler": "does_not_exist.js"}
            ]
            self.assertFalse(manager.validate_hooks())

    def test_disabled_hook_with_missing_handler_is_still_valid(self):
        # handler existence is only checked for *enabled* hooks
        with tempfile.TemporaryDirectory() as tmp:
            manager = HookManager(Path(tmp))
            manager.hooks = [
                {"id": "x", "type": "PreToolUse", "enabled": False, "handler": "does_not_exist.js"}
            ]
            self.assertTrue(manager.validate_hooks())


class TestFormatForClaudeConfig(unittest.TestCase):
    def test_only_enabled_hooks_with_all_required_fields_included(self):
        manager = HookManager(Path("/project"))
        manager.hooks = [
            {"id": "a", "type": "PreToolUse", "enabled": True, "handler": "hooks/a.js", "description": "d"},
            {"id": "b", "type": "PreToolUse", "enabled": False, "handler": "hooks/b.js"},
            {"id": "c", "type": "PostToolUse", "enabled": True, "handler": None},  # missing handler
        ]
        result = manager.format_for_claude_config()
        self.assertIn("PreToolUse", result)
        self.assertEqual(len(result["PreToolUse"]), 1)
        self.assertEqual(result["PreToolUse"][0]["id"], "a")
        self.assertNotIn("PostToolUse", result)  # "c" was excluded (no handler)


if __name__ == "__main__":
    unittest.main()
