# Contributing

## Commit messages

Commits follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>: <short summary>
```

Types used in this repo:

| Type    | When to use it                                              |
|---------|---------------------------------------------------------------|
| `feat`  | A new feature or capability                                   |
| `fix`   | A bug fix                                                      |
| `docs`  | Documentation only (README, ARCHITECTURE.md, comments)        |
| `test`  | Adding or updating tests, CI config                            |
| `chore` | Everything else - refactors, tooling, dependency bumps, etc.   |

Examples, from this repo's own history:

```
feat: initial Yantra launcher with token optimization
test: add test suite + CI, honest version/status framing
docs: add ARCHITECTURE.md - design decisions, why, and FAQ
fix: correct stale section anchors in ARCHITECTURE.md; update README author info
chore: derive version dynamically from config instead of hardcoding
```

This is a documented convention, not an enforced one - there's no commit
hook or CI check rejecting messages that don't match. Follow it so history
stays scannable and greppable (`git log --grep '^feat:'`), but don't block
on it.
