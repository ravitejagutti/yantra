"""Tests for launcher.config.ConfigLoader / YantraConfig.

No external dependencies needed - just temp directories and JSON files.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from launcher.config import ConfigLoader, YantraConfig


class TestYantraConfigDefaults(unittest.TestCase):
    def test_headroom_defaults_to_enabled_with_no_args(self):
        config = YantraConfig()
        self.assertEqual(config.headroom, {"enabled": True, "args": []})

    def test_empty_collections_by_default(self):
        config = YantraConfig()
        self.assertEqual(config.skills, {})
        self.assertEqual(config.hooks, {})
        self.assertEqual(config.environment, {})
        self.assertEqual(config.system_prompt_template, "")


class TestConfigLoaderLoad(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.config_dir = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _write(self, filename, content):
        (self.config_dir / filename).write_text(content)

    def test_missing_config_files_produce_defaults_not_errors(self):
        # No files at all in the directory - load() should not raise.
        loader = ConfigLoader(self.config_dir)
        config = loader.load()
        self.assertEqual(config.headroom, {"enabled": True, "args": []})
        self.assertEqual(config.environment, {})

    def test_loads_headroom_settings_from_yantra_config_json(self):
        self._write(
            "yantra.config.json",
            json.dumps({"headroom": {"enabled": False, "args": ["--no-mcp"]}}),
        )
        loader = ConfigLoader(self.config_dir)
        config = loader.load()
        self.assertEqual(config.headroom, {"enabled": False, "args": ["--no-mcp"]})

    def test_headroom_config_merges_over_defaults_not_replaces(self):
        # Only "args" specified - "enabled" should still come from the default.
        self._write(
            "yantra.config.json",
            json.dumps({"headroom": {"args": ["--memory"]}}),
        )
        loader = ConfigLoader(self.config_dir)
        config = loader.load()
        self.assertEqual(config.headroom, {"enabled": True, "args": ["--memory"]})

    def test_loads_environment_block(self):
        self._write(
            "yantra.config.json",
            json.dumps({"environment": {"MY_VAR": "hello"}}),
        )
        loader = ConfigLoader(self.config_dir)
        config = loader.load()
        self.assertEqual(config.environment, {"MY_VAR": "hello"})

    def test_loads_skills_block(self):
        self._write(
            "yantra.config.json",
            json.dumps({"skills": {"context_analysis": {"enabled": True}}}),
        )
        loader = ConfigLoader(self.config_dir)
        config = loader.load()
        self.assertIn("context_analysis", config.skills)

    def test_invalid_json_raises_value_error(self):
        self._write("yantra.config.json", "{ not valid json")
        loader = ConfigLoader(self.config_dir)
        with self.assertRaises(ValueError):
            loader.load()

    def test_loads_system_prompt_text(self):
        self._write("system-prompt.md", "# Hello\nSome instructions.")
        loader = ConfigLoader(self.config_dir)
        config = loader.load()
        self.assertIn("Some instructions.", config.system_prompt_template)

    def test_hooks_json_merges_into_config_hooks(self):
        self._write("hooks.json", json.dumps({"hooks": [{"id": "safety_gates"}]}))
        loader = ConfigLoader(self.config_dir)
        config = loader.load()
        self.assertIn("hooks", config.hooks)
        self.assertEqual(config.hooks["hooks"][0]["id"], "safety_gates")


class TestEnvironmentSubstitution(unittest.TestCase):
    def setUp(self):
        os.environ["YANTRA_TEST_VAR"] = "substituted-value"

    def tearDown(self):
        os.environ.pop("YANTRA_TEST_VAR", None)

    def test_substitutes_known_variable(self):
        loader = ConfigLoader(Path("."))
        config = YantraConfig(system_prompt_template="Value: ${YANTRA_TEST_VAR}")
        loader.substitute_environment(config)
        self.assertEqual(config.system_prompt_template, "Value: substituted-value")

    def test_unknown_variable_is_left_unchanged(self):
        loader = ConfigLoader(Path("."))
        config = YantraConfig(system_prompt_template="Value: ${YANTRA_DOES_NOT_EXIST}")
        loader.substitute_environment(config)
        self.assertEqual(config.system_prompt_template, "Value: ${YANTRA_DOES_NOT_EXIST}")

    def test_substitutes_in_environment_dict_values(self):
        loader = ConfigLoader(Path("."))
        config = YantraConfig(environment={"GREETING": "hi ${YANTRA_TEST_VAR}"})
        loader.substitute_environment(config)
        self.assertEqual(config.environment["GREETING"], "hi substituted-value")


if __name__ == "__main__":
    unittest.main()
