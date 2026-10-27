# CLAUDE.md

Rules for a Claude Code session working in this repository. The contract every session loads is `core/AGENTS.md`, and this file imports it:

@core/AGENTS.md

Repo rules:

- Every hook is one Python 3 file that uses only the standard library. Do not add a dependency.
- A hook that denies a tool call must fail open on its own errors.
- `analyzer-action/analyzer.js` mirrors the analyzer page. Run `node analyzer-action/sync.js <page> --check` before committing a change to either.
- Run `bash tests/lint/test_lint.sh` before every commit.
- Never commit a secret, a personal name, an email address or a hostname. The lint fails on private identifiers in shared files.
- Say in the README when something is untested. Update `CHANGELOG.md` with every change a user can see.
