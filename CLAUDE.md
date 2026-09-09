# Project instructions for Claude Code

## Git & GitHub guardrails

- **Never commit or push without an explicit go-ahead for that specific
  change.** A forward-looking "do whatever you think is best" earlier in
  the conversation doesn't count as standing authorization - ask again
  right before the actual commit/push.
- **Before committing, show the actual change, not just which files
  changed.** `git status --short` (one path per line, with its status
  letter) is fine for catching scope creep on a multi-file commit, but on
  its own it's not enough to approve anything - it says nothing about
  content. Pair it with the real diff: full `git diff` for small/medium
  changes, `git diff --stat` (file names + insertion/deletion counts) for
  large ones, with the full diff available on request. Plus the exact
  commit message. Wait for confirmation - don't commit first and
  summarize after. Run these checks live, on the real working tree, at
  that moment - not from memory, and before anything's been
  staged/committed away.
- **Before pushing, show exactly which commits are about to go out** -
  `git log --oneline <upstream>..HEAD` (or against whatever remote branch
  is being pushed to, if there's no upstream tracked yet), one commit per
  line. The working-tree diff check above is empty by this point since
  everything's already committed - this is the push-time equivalent, and
  it's a separate check, not covered by having already confirmed the
  commit(s) individually earlier.
- **Commit messages must start with a [Conventional Commits](https://www.conventionalcommits.org/)
  type prefix** per [CONTRIBUTING.md](CONTRIBUTING.md) (`feat`, `fix`,
  `docs`, `test`, `chore`) - lowercase. This applies to any commit being
  added to a branch, including checking that pre-existing commits already
  on that branch (e.g. auto-generated ones) also follow it. Nothing beyond
  the prefix is restricted - the summary line and body are free-form.
- **Force-push, deleting a file/branch, or anything else similarly hard
  to reverse needs its own interactive confirmation, every single time**
  - show the exact command about to run and wait for an explicit yes
  right before running it. A general "go ahead" given earlier for the
  broader task does not cover this - ask again at the moment it's about
  to happen, no exceptions. Force-push specifically: always
  `--force-with-lease`, never bare `--force`.
- **If a file about to be deleted or overwritten has unexpected state**
  (uncommitted changes Claude didn't make, unfamiliar content), stop and
  show it before proceeding, rather than assuming it's fine to lose - on
  top of, not instead of, the confirmation above.
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
