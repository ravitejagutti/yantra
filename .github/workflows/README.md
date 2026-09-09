# Workflows

## `tests.yml`
Runs the test suite (`python -m unittest discover -s tests`) on every push and
PR. Plain CI, no external dependencies, no secrets involved.

## `claude-code-review.yml`
Auto-reviews every PR - triggers on open, push, un-drafting, and reopen.
Uses Anthropic's official `code-review` plugin to post inline comments.

- **Skips draft PRs** (`if: draft == false`) - only reviews once the author
  marks it ready.
- **Cancels stale runs** (`concurrency` group per PR number) - push again
  before a review finishes, and the old run gets cancelled instead of both
  completing and billing separately.
- **Read-only.** Can post comments, can't push commits or resolve review
  threads. If it flags something, fixing it and marking the thread resolved
  is still a manual step, same as feedback from a human reviewer. See
  `permissions:` in the file for the exact scopes.

## `claude.yml`
Responds when `@claude` is mentioned in an issue, a PR comment, an inline
review comment, or a submitted review. Nothing runs unless that exact text
is present - the `if:` condition re-checks it per event.

Unlike the review workflow above, no fixed `prompt:` is set, so it does
whatever's asked in the comment that mentioned it (explain a diff, answer a
question, look at why CI failed via `actions: read`, etc.) - still bounded
by the same read-only `permissions:` scopes.

## Auth
Both Claude workflows authenticate via `secrets.CLAUDE_CODE_OAUTH_TOKEN`,
set through `/install-github-app` (repo Settings → Secrets → Actions).
Nothing in these files is a hardcoded credential.

## Why nothing here can auto-fix or auto-resolve
Both workflows are deliberately kept read-only (`contents: read`,
`pull-requests: read`). Auto-resolving review threads or pushing fixes
would need write access, and would mean trusting Claude's own judgment
that its own feedback was correctly addressed, with no human check in
between. Not worth trading away the safety of read-only for the small
amount of manual effort (clicking "Resolve conversation") it would save.
Revisit if/when this repo has enough contributors that manual review-thread
cleanup becomes a real bottleneck.

See [`anthropics/claude-code-action` docs](https://github.com/anthropics/claude-code-action/blob/main/docs/usage.md)
for the full list of inputs these files can use.
