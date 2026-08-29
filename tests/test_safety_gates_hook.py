"""Tests for hooks/safety_gates.js - the actual Claude Code PreToolUse hook.

Runs the real script via `node`, feeding it JSON on stdin exactly the way
Claude Code does, and checking its stdout JSON decision - this is the real
protocol (https://code.claude.com/docs/en/hooks), not a mock of it. Skipped
automatically if `node` isn't on PATH (Node.js is a hard project
requirement per README, but CI environments vary).
"""

import json
import shutil
import subprocess
import unittest
from pathlib import Path

HOOK_SCRIPT = Path(__file__).resolve().parent.parent / "hooks" / "safety_gates.js"

NODE_AVAILABLE = shutil.which("node") is not None


def run_hook(payload: dict) -> dict:
    """Feed `payload` to safety_gates.js on stdin, parse its stdout JSON."""
    result = subprocess.run(
        ["node", str(HOOK_SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )
    return json.loads(result.stdout)


def is_denied(decision: dict) -> bool:
    return decision.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


@unittest.skipUnless(NODE_AVAILABLE, "node not found on PATH")
class TestSafetyGatesHook(unittest.TestCase):
    def test_safe_bash_command_is_allowed(self):
        decision = run_hook({"tool_name": "Bash", "tool_input": {"command": "ls -la"}})
        self.assertFalse(is_denied(decision))

    def test_rm_rf_is_blocked(self):
        decision = run_hook({"tool_name": "Bash", "tool_input": {"command": "rm -rf /tmp/foo"}})
        self.assertTrue(is_denied(decision))

    def test_git_reset_hard_is_blocked(self):
        decision = run_hook({"tool_name": "Bash", "tool_input": {"command": "git reset --hard HEAD~3"}})
        self.assertTrue(is_denied(decision))

    def test_git_push_force_is_blocked(self):
        decision = run_hook({"tool_name": "Bash", "tool_input": {"command": "git push origin main --force"}})
        self.assertTrue(is_denied(decision))

    def test_drop_table_is_blocked(self):
        decision = run_hook({"tool_name": "Bash", "tool_input": {"command": "psql -c 'DROP TABLE users;'"}})
        self.assertTrue(is_denied(decision))

    def test_powershell_remove_item_recurse_is_blocked(self):
        decision = run_hook({"tool_name": "PowerShell", "tool_input": {"command": "Remove-Item -Recurse C:\\temp"}})
        self.assertTrue(is_denied(decision))

    def test_non_shell_tool_is_always_allowed(self):
        """Only Bash/PowerShell are guarded - a destructive-looking string
        in, say, a file path for the Read tool must not be blocked."""
        decision = run_hook({"tool_name": "Read", "tool_input": {"file_path": "rm -rf notes.txt"}})
        self.assertFalse(is_denied(decision))

    def test_malformed_input_fails_open(self):
        """Critical safety property: a bug or unexpected input shape must
        never accidentally block every tool call globally."""
        result = subprocess.run(
            ["node", str(HOOK_SCRIPT)],
            input="not valid json at all",
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0)
        decision = json.loads(result.stdout)
        self.assertFalse(is_denied(decision))

    def test_missing_tool_input_does_not_crash(self):
        decision = run_hook({"tool_name": "Bash"})
        self.assertFalse(is_denied(decision))

    def test_process_always_exits_zero(self):
        """The hook communicates its decision via JSON, not exit code -
        exit 2 would ALSO block per the protocol, so it must stick to 0."""
        result = subprocess.run(
            ["node", str(HOOK_SCRIPT)],
            input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}),
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
