#!/usr/bin/env node
/**
 * Safety Gates - Claude Code PreToolUse hook
 *
 * Blocks destructive shell commands before Claude executes them. This is a
 * standalone script invoked by Claude Code itself (registered via
 * ~/.claude/settings.json - see `yantra install`), not a module imported by
 * Yantra's Python launcher.
 *
 * Protocol (https://code.claude.com/docs/en/hooks):
 * - Claude Code writes the hook-event JSON to this process's stdin.
 * - This script writes a JSON decision to stdout and exits 0.
 * - {"hookSpecificOutput": {..., "permissionDecision": "deny", ...}} blocks
 *   the call; {} (or any output without permissionDecision) allows it.
 * - Any parse error or unexpected shape fails OPEN (allows), on purpose:
 *   a bug here should never be able to block every tool call globally.
 *
 * Author: Ravi Teja Gutakonda
 * License: MIT
 */

const BLOCKED_PATTERNS = [
  { pattern: /rm\s+-rf/i, label: "rm -rf (file deletion)" },
  { pattern: /Remove-Item\s+.*-Recurse/i, label: "Remove-Item -Recurse (file deletion)" },
  { pattern: /git\s+reset\s+--hard/i, label: "git reset --hard (discard work)" },
  { pattern: /git\s+rebase\s+-i/i, label: "git rebase -i (interactive rebase)" },
  { pattern: /DELETE\s+FROM/i, label: "DELETE FROM (database delete)" },
  { pattern: /DROP\s+TABLE/i, label: "DROP TABLE (remove table)" },
  { pattern: /truncate\s+table/i, label: "truncate table (clear table)" },
  { pattern: /git\s+push[^|;&]*--force/i, label: "git push --force (force push)" },
];

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => (data += chunk));
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });
}

function allow() {
  process.stdout.write("{}");
  process.exit(0);
}

function deny(reason) {
  process.stdout.write(
    JSON.stringify({
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "deny",
        permissionDecisionReason: reason,
      },
    })
  );
  process.exit(0);
}

async function main() {
  let input;
  try {
    input = JSON.parse(await readStdin());
  } catch {
    return allow(); // Malformed input - fail open, never block on a bug.
  }

  const toolName = input && input.tool_name;
  if (toolName !== "Bash" && toolName !== "PowerShell") {
    return allow();
  }

  const command = input.tool_input && input.tool_input.command;
  if (!command || typeof command !== "string") {
    return allow();
  }

  for (const { pattern, label } of BLOCKED_PATTERNS) {
    if (pattern.test(command)) {
      const preview = command.length > 80 ? command.slice(0, 77) + "..." : command;
      return deny(
        `Yantra safety gate blocked this command: ${label}\n` +
          `Command: ${preview}\n\n` +
          `If this is genuinely intended, ask the user to confirm explicitly, ` +
          `or have them run it manually outside this session.`
      );
    }
  }

  return allow();
}

main().catch(() => allow()); // Any unexpected error - fail open.
