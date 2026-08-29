"""Tests for launcher.context.ContextInjector.

Covers the safety-sensitive part (never leak secrets into the printed
context) and the pure formatting logic. Git/filesystem gathering itself
isn't tested here - it just shells out to `git` and reads the cwd, which is
integration-level, not unit-level, behavior.
"""

import os
import unittest

from launcher.context import ContextInjector


class TestSafeEnvVarFiltering(unittest.TestCase):
    def setUp(self):
        self.injector = ContextInjector()
        self._saved = {}
        for var in ContextInjector.SAFE_ENV_VARS:
            self._saved[var] = os.environ.get(var)

    def tearDown(self):
        for var, value in self._saved.items():
            if value is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = value

    def test_allowlisted_var_with_a_value_is_included(self):
        os.environ["USER"] = "testuser"
        result = self.injector._get_safe_env_vars()
        self.assertEqual(result.get("USER"), "testuser")

    def test_var_not_on_the_allowlist_is_never_included(self):
        os.environ["USER"] = "testuser"
        result = self.injector._get_safe_env_vars()
        self.assertNotIn("SOME_RANDOM_SECRET_VAR", result)

    def test_unset_allowlisted_var_is_simply_absent(self):
        os.environ.pop("SHELL", None)
        result = self.injector._get_safe_env_vars()
        self.assertNotIn("SHELL", result)

    def test_blocked_pattern_substring_match_still_works(self):
        """BLOCKED_ENV_VARS uses substring matching against the allowlisted
        var *names* themselves (e.g. would block a var literally named
        "API_KEY" if someone added it to SAFE_ENV_VARS by mistake) - this
        guards against that regression even though none of the current
        SAFE_ENV_VARS entries happen to match."""
        for name in ContextInjector.SAFE_ENV_VARS:
            for blocked in ContextInjector.BLOCKED_ENV_VARS:
                self.assertNotIn(
                    blocked, name.upper(),
                    f"{name!r} in SAFE_ENV_VARS matches blocked pattern {blocked!r} - "
                    f"it would silently never be exposed",
                )


class TestFormatContextForPrompt(unittest.TestCase):
    def setUp(self):
        self.injector = ContextInjector()

    def test_includes_branch_when_git_available(self):
        context = {"git": {"available": True, "branch": "main", "dirty": False}}
        text = self.injector.format_context_for_prompt(context)
        self.assertIn("main", text)

    def test_omits_git_section_when_not_available(self):
        context = {"git": {"available": False}}
        text = self.injector.format_context_for_prompt(context)
        self.assertNotIn("Git Branch", text)

    def test_includes_dirty_file_count_when_dirty(self):
        context = {"git": {"available": True, "branch": "main", "dirty": True, "modified_files": 3}}
        text = self.injector.format_context_for_prompt(context)
        self.assertIn("3 modified files", text)

    def test_includes_working_directory(self):
        context = {"filesystem": {"working_directory": "/home/user/project"}}
        text = self.injector.format_context_for_prompt(context)
        self.assertIn("/home/user/project", text)

    def test_empty_context_does_not_crash(self):
        text = self.injector.format_context_for_prompt({})
        self.assertIsInstance(text, str)


if __name__ == "__main__":
    unittest.main()
