# CLAUDE.md check

Short install line from the standalone mirror: `uses: steward-kit/claude-md-check@v0.1.1` (https://github.com/steward-kit/claude-md-check)

This action reads your CLAUDE.md, counts the rule-like lines, and shows which ones a steward-kit hook can enforce. The report lands in the job summary. By default it never fails a build.

```yaml
on: pull_request
jobs:
  claude-md:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: steward-kit/steward-kit/analyzer-action@main
```

## Inputs

- `path`: rules file to check, relative to the workspace. Default `CLAUDE.md`.
- `fail-under`: a number. If `enforceable_percent` is below it, the step exits 1. Default empty, so it never fails.

## Outputs

- `rules`: count of rule-like lines.
- `matched`: lines the catalog matches.
- `enforceable_percent`: matched divided by rules, one decimal. 0 when there are no rules.

If the file is missing, the step says so and exits 0.

Nothing is uploaded anywhere. It runs in your workflow's own runner.

The catalog is the steward-kit hook set. A rule it does not match may still be enforceable another way.

Maintainers: `analyzer.js` is generated. Refresh it with `node sync.js <analyzer page>`, and check it with `node sync.js <analyzer page> --check`.
