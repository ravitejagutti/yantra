# Project instructions for Claude Code

## Git & GitHub guardrails

- **Never commit or push without an explicit go-ahead for that specific
  change.** A forward-looking "do whatever you think is best" earlier in
  the conversation doesn't count as standing authorization - ask again
  right before the actual commit/push.
- **Before committing, list the exact files changed and the exact commit
  message, and wait for confirmation.** Don't commit first and summarize
  after.
- **Commit messages must start with a [Conventional Commits](https://www.conventionalcommits.org/)
  type prefix** per [CONTRIBUTING.md](CONTRIBUTING.md) (`feat`, `fix`,
  `docs`, `test`, `chore`) - lowercase. This applies to any commit being
  added to a branch, including checking that pre-existing commits already
  on that branch (e.g. auto-generated ones) also follow it. Nothing beyond
  the prefix is restricted - the summary line and body are free-form.
- **Force-push needs its own explicit confirmation**, separate from a
  normal push confirmation - it rewrites history that may already be
  public. Always `--force-with-lease`, never bare `--force`.
- **If a file about to be deleted or overwritten has unexpected state**
  (uncommitted changes Claude didn't make, unfamiliar content), stop and
  show it before proceeding, rather than assuming it's fine to lose.
- **State the current branch before every commit/push.** If work happens
  on a non-default or PR branch, switch back to the user's working branch
  afterward and say so.
- **Never run interactive/browser-based auth commands** (`gh auth login`,
  `gh auth refresh`, etc.) - give the user the exact command to run
  themselves instead.
- **Run the test suite before pushing**, and report pass/fail explicitly.
- **Don't commit directly to a base branch** (`yantra/initial-pilot`,
  `main`). Branch off it first, and name the new branch `<project>/<name>`
  (e.g. `yantra/add-branch-naming-guardrail`) - matching the
  `yantra/initial-pilot` pattern already in use.
