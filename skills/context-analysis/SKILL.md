---
name: context-analysis
description: Summarizes the current git branch, uncommitted changes, and working directory. Use when the user asks what changed, wants repo context, a diff summary, or "what's going on here".
---

## Git branch and status

!`git status --short --branch 2>&1`

## Uncommitted changes (stat)

!`git diff --stat HEAD 2>&1`

## Working directory

!`pwd`

## Instructions

Summarize the branch, working directory, and any uncommitted changes above in
a few short bullet points. If the git commands errored (not a git repo, no
commits yet), say so plainly instead of guessing. Flag anything that looks
risky - large deletions, an unexpectedly large diff, or files outside the
expected project - so the user notices before acting on it.
