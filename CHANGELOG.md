# Changelog

## 0.1.1 - 2026-10-26

- `analyzer-action/`: a composite GitHub Action that runs the CLAUDE.md analyzer in CI, writes the report to the job summary and never fails a build unless `fail-under` is set. `analyzer.js` is generated from the site's analyzer page; `node sync.js <page> --check` catches drift.

## 0.1.0 - 2026-10-26

First public copy of the free tier.

- Kit skeleton: contract, scout and worker agents, memory schema, lint and its test, with only the `_template` and `lab` profiles and a blank machine template.
- Hooks pack: twelve hooks, all paths and names moved to environment variables with defaults, plus a registration snippet and an example caps file.
