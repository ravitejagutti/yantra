"""Tests for launcher.claude_extras (`yantra install` / `yantra uninstall`).

These tests NEVER touch the real ~/.claude/ or this repo's real hooks/ and
skills/ - every test redirects HOOKS_SOURCE_DIR, SKILLS_SOURCE_DIR,
CLAUDE_SETTINGS_PATH, SKILLS_INSTALL_DIR, and SKILLS_MANIFEST_PATH to an
isolated temp directory first. install()/uninstall() mutate a real user's
global Claude Code config, so getting the discovery/sync/idempotency/
non-destructiveness logic right here matters more than almost anything else
in this codebase.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from launcher import claude_extras as ce


class ClaudeExtrasTestCase(unittest.TestCase):
    """Base class: redirects every path claude_extras reads/writes to an
    isolated temp directory (a fake repo side and a fake home side), and
    restores the real paths afterward."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)

        self._orig = {
            name: getattr(ce, name)
            for name in (
                "HOOKS_SOURCE_DIR",
                "SKILLS_SOURCE_DIR",
                "CLAUDE_SETTINGS_PATH",
                "SKILLS_INSTALL_DIR",
                "SKILLS_MANIFEST_PATH",
            )
        }

        ce.HOOKS_SOURCE_DIR = root / "repo" / "hooks"
        ce.SKILLS_SOURCE_DIR = root / "repo" / "skills"
        ce.CLAUDE_SETTINGS_PATH = root / "home" / "settings.json"
        ce.SKILLS_INSTALL_DIR = root / "home" / "skills"
        ce.SKILLS_MANIFEST_PATH = ce.SKILLS_INSTALL_DIR / ".yantra-manifest.json"

        self.hooks_dir = ce.HOOKS_SOURCE_DIR
        self.skills_dir = ce.SKILLS_SOURCE_DIR

    def tearDown(self):
        for name, value in self._orig.items():
            setattr(ce, name, value)
        self.tmpdir.cleanup()

    def write_hook(self, name="safety_gates.js", content="// fake hook\n"):
        self.hooks_dir.mkdir(parents=True, exist_ok=True)
        path = self.hooks_dir / name
        path.write_text(content)
        return path

    def write_skill(self, name="context-analysis", content="# Skill\n"):
        skill_dir = self.skills_dir / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(content)
        return skill_dir


class TestDiscoverHooks(ClaudeExtrasTestCase):
    def test_no_hooks_dir_returns_empty(self):
        self.assertEqual(ce.discover_hooks(), [])

    def test_ignores_non_js_files(self):
        self.write_hook("safety_gates.js")
        (self.hooks_dir / "README.md").write_text("not a hook")
        self.assertEqual([p.name for p in ce.discover_hooks()], ["safety_gates.js"])

    def test_finds_multiple_sorted(self):
        self.write_hook("z_hook.js")
        self.write_hook("a_hook.js")
        self.assertEqual([p.name for p in ce.discover_hooks()], ["a_hook.js", "z_hook.js"])


class TestDiscoverSkills(ClaudeExtrasTestCase):
    def test_no_skills_dir_returns_empty(self):
        self.assertEqual(ce.discover_skills(), [])

    def test_requires_skill_md(self):
        empty_dir = self.skills_dir / "not-a-skill"
        empty_dir.mkdir(parents=True)
        (empty_dir / "notes.txt").write_text("no SKILL.md here")
        self.assertEqual(ce.discover_skills(), [])

    def test_finds_valid_skill(self):
        self.write_skill("context-analysis")
        self.assertEqual([p.name for p in ce.discover_skills()], ["context-analysis"])


class TestSyncHooks(ClaudeExtrasTestCase):
    def test_adds_new_matcher_groups_when_none_exist(self):
        script = self.write_hook("safety_gates.js")
        settings = {}
        ce._sync_hooks(settings, [script], "node")
        matchers = {g["matcher"] for g in settings["hooks"]["PreToolUse"]}
        self.assertEqual(matchers, set(ce.GUARDED_MATCHERS))

    def test_appends_without_touching_unrelated_hooks(self):
        script = self.write_hook("safety_gates.js")
        settings = {
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo", "args": ["unrelated"]}]}
                ]
            }
        }
        ce._sync_hooks(settings, [script], "node")
        hooks = next(g for g in settings["hooks"]["PreToolUse"] if g["matcher"] == "Bash")["hooks"]
        self.assertEqual(len(hooks), 2)
        self.assertTrue(any(h["args"] == ["unrelated"] for h in hooks))

    def test_resync_replaces_stale_entry_instead_of_duplicating(self):
        """The core idempotency guarantee: syncing twice must not produce
        two copies of the same hook."""
        script = self.write_hook("safety_gates.js")
        settings = {}
        ce._sync_hooks(settings, [script], "node_old")
        ce._sync_hooks(settings, [script], "node_new")
        hooks = next(g for g in settings["hooks"]["PreToolUse"] if g["matcher"] == "Bash")["hooks"]
        self.assertEqual(len(hooks), 1)
        self.assertEqual(hooks[0]["command"], "node_new")

    def test_added_hook_file_is_picked_up_on_resync(self):
        script_a = self.write_hook("a_hook.js")
        settings = {}
        ce._sync_hooks(settings, [script_a], "node")
        script_b = self.write_hook("b_hook.js")
        ce._sync_hooks(settings, [script_a, script_b], "node")
        hooks = next(g for g in settings["hooks"]["PreToolUse"] if g["matcher"] == "Bash")["hooks"]
        self.assertEqual(len(hooks), 2)

    def test_removed_hook_file_is_pruned_on_resync(self):
        script_a = self.write_hook("a_hook.js")
        script_b = self.write_hook("b_hook.js")
        settings = {}
        ce._sync_hooks(settings, [script_a, script_b], "node")
        ce._sync_hooks(settings, [script_a], "node")  # b_hook.js gone from repo
        hooks = next(g for g in settings["hooks"]["PreToolUse"] if g["matcher"] == "Bash")["hooks"]
        self.assertEqual(len(hooks), 1)
        self.assertTrue(hooks[0]["args"][0].endswith("a_hook.js"))

    def test_syncing_to_empty_drops_matcher_groups(self):
        script = self.write_hook("safety_gates.js")
        settings = {}
        ce._sync_hooks(settings, [script], "node")
        ce._sync_hooks(settings, [], "node")
        self.assertEqual(settings["hooks"]["PreToolUse"], [])


class TestRemoveHook(ClaudeExtrasTestCase):
    def test_removes_only_yantras_own_entries(self):
        script = self.write_hook("safety_gates.js")
        settings = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {"type": "command", "command": "echo", "args": ["unrelated"]},
                            {"type": "command", "command": "node", "args": [str(script)]},
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
        script = self.write_hook("safety_gates.js")
        settings = {
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Bash", "hooks": [{"type": "command", "command": "node", "args": [str(script)]}]}
                ]
            }
        }
        ce._remove_hook(settings)
        self.assertEqual(settings["hooks"]["PreToolUse"], [])

    def test_nothing_to_remove_returns_false(self):
        self.assertFalse(ce._remove_hook({}))


class TestSyncSkills(ClaudeExtrasTestCase):
    def test_copies_skill_into_install_dir(self):
        self.write_skill("context-analysis", content="# hi\n")
        installed = ce._sync_skills(ce.discover_skills())
        self.assertEqual(installed, ["context-analysis"])
        self.assertTrue((ce.SKILLS_INSTALL_DIR / "context-analysis" / "SKILL.md").exists())

    def test_resync_picks_up_content_changes(self):
        self.write_skill("context-analysis", content="v1\n")
        ce._sync_skills(ce.discover_skills())
        self.write_skill("context-analysis", content="v2\n")
        ce._sync_skills(ce.discover_skills())
        content = (ce.SKILLS_INSTALL_DIR / "context-analysis" / "SKILL.md").read_text()
        self.assertEqual(content, "v2\n")

    def test_added_skill_is_picked_up_on_resync(self):
        self.write_skill("a-skill")
        ce._sync_skills(ce.discover_skills())
        self.write_skill("b-skill")
        ce._sync_skills(ce.discover_skills())
        self.assertTrue((ce.SKILLS_INSTALL_DIR / "b-skill").exists())

    def test_removed_skill_is_pruned_on_resync(self):
        self.write_skill("a-skill")
        self.write_skill("b-skill")
        ce._sync_skills(ce.discover_skills())
        shutil.rmtree(self.skills_dir / "b-skill")  # b-skill gone from repo
        ce._sync_skills(ce.discover_skills())
        self.assertFalse((ce.SKILLS_INSTALL_DIR / "b-skill").exists())
        self.assertTrue((ce.SKILLS_INSTALL_DIR / "a-skill").exists())

    def test_never_touches_a_skill_it_did_not_install(self):
        """A skill directory the user added to ~/.claude/skills by hand
        (never in Yantra's manifest) must survive sync/removal untouched."""
        ce.SKILLS_INSTALL_DIR.mkdir(parents=True, exist_ok=True)
        hand_added = ce.SKILLS_INSTALL_DIR / "hand-added"
        hand_added.mkdir()
        (hand_added / "SKILL.md").write_text("mine")

        self.write_skill("context-analysis")
        ce._sync_skills(ce.discover_skills())
        ce._remove_skills()

        self.assertTrue(hand_added.exists())


class TestInstallUninstallEndToEnd(ClaudeExtrasTestCase):
    """Full install()/uninstall() cycle against the isolated fake repo/home."""

    def setUp(self):
        super().setUp()
        self.node_patch = patch.object(ce, "find_node_executable", return_value="/usr/bin/node")
        self.node_patch.start()
        self.write_hook("safety_gates.js")
        self.write_skill("context-analysis")

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
        self.assertTrue((ce.SKILLS_INSTALL_DIR / "context-analysis" / "SKILL.md").exists())

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

    def test_install_picks_up_a_newly_added_hook(self):
        ce.install()
        self.write_hook("extra_gate.js")
        ce.install()
        data = json.loads(ce.CLAUDE_SETTINGS_PATH.read_text())
        bash_group = next(g for g in data["hooks"]["PreToolUse"] if g["matcher"] == "Bash")
        self.assertEqual(len(bash_group["hooks"]), 2)

    def test_install_picks_up_a_newly_added_skill(self):
        ce.install()
        self.write_skill("another-skill")
        ce.install()
        self.assertTrue((ce.SKILLS_INSTALL_DIR / "another-skill" / "SKILL.md").exists())

    def test_uninstall_removes_exactly_what_install_added(self):
        ce.install()
        rc = ce.uninstall()
        self.assertEqual(rc, 0)
        self.assertFalse((ce.SKILLS_INSTALL_DIR / "context-analysis").exists())
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
