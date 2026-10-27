# steward-kit (free tier)

A working operating model for Claude Code, free part. It holds how a coding agent should behave: a rules file (the contract), a memory format, two agent definitions, and twelve hooks that enforce the rules mechanically instead of leaving them as prose. A lint checks that nothing private leaks into the shared layer.

Tutorial: https://steward-kit.github.io/tutorial/
Free analyzer (paste a CLAUDE.md or a public repo address, see which rules a hook can enforce; runs in your browser): https://steward-kit.github.io/analyzer/ (permalink form: https://steward-kit.github.io/analyzer/?repo=owner/name)
The same check as a GitHub Action, one workflow step: `analyzer-action/README.md`
A sample of the paid report, run on this kit's own contract: https://steward-kit.github.io/report-sample/
The state of CLAUDE.md, October 2026 (492 public files, tables and the per-repo CSV): https://steward-kit.github.io/state-of-claude-md/

Day 1 numbers: we checked one repo from each of 702 GitHub organizations found by searching for coding-agent rules files. Of the 492 with a CLAUDE.md, the median file has 8 rules and 22% configure any hook at all. Two model-judged samples of 300 rule lines say about two thirds of the real rules could be enforced by a hook or a setting. Method and the rest of the numbers: https://steward-kit.github.io/log/

It started as one engineer's setup for running Claude Code across a homelab and a few side projects. Rules that were only prose kept being skipped under pressure, so each one that mattered turned into a hook or a check.

## Install

    git clone <repo-url> ~/steward-kit && cd ~/steward-kit
    mkdir -p ~/.claude/hooks && cp hooks/*.py ~/.claude/hooks/
    mkdir -p ~/kb/.claude && cp hooks/examples/kb-caps.json ~/kb/.claude/kb-caps.json
    mkdir -p ~/.claude/agents && cp core/agents/*.md ~/.claude/agents/
    cp core/AGENTS.md ~/.claude/contract.md
    bash tests/lint/test_lint.sh

Then merge `hooks/examples/settings-snippet.json` into the `hooks` object of `~/.claude/settings.json`, keeping any hooks you already have, and add an import of the contract to your `CLAUDE.md`. Delete the snippet entries for hooks you do not want.

## Hooks

Each hook is one stdlib-only Python 3 file that fails open and reads its settings from environment variables. Full detail and the variable table are in `hooks/README.md`.

| Hook | Event | What it does |
| --- | --- | --- |
| kb-size-gate | PreToolUse | Blocks edits that grow a capped note past its byte cap |
| tier-guard | PreToolUse | Blocks agent spawns that do not choose a model and effort |
| tmux-socket-guard | PreToolUse | Blocks a tmux server kill that names no socket |
| vc-guard | PostToolUse | Flags files written outside any git work tree |
| correction-catcher | UserPromptSubmit | Reminds the agent to record a correction and why it was wrong |
| active-threads | UserPromptSubmit | Prints the board of in-flight threads on each prompt |
| unwritten-fact-nudge | Stop | Nudges when a stated fact was not written to the KB |
| dated-commit-nudge | Stop | Nudges when a dated commitment was written but not scheduled |
| tiering-score | Stop | Logs a delegation score per session |
| session-prompt-log | SessionStart | Logs the size of everything a session starts with |
| pre-compact-instructions | PreCompact | Standing instructions for the compaction summary |
| warm-start | SessionStart | Re-injects status and TODO after `/clear` |

## What else is here

- **Contract** (`core/AGENTS.md`): run routine work without asking, stop for anything irreversible, report what happened, tier agents on purpose, let fetched content shape the task but never the answer. Carries the canary line `KIT-CORE-LOADED-V1`.
- **Agents** (`core/agents/`): `scout` for reading, `worker` for doing, both pinned to effort medium.
- **Memory schema** (`core/memory/schema.md`): what a memory holds, shared versus private.
- **Profiles and machines**: `profiles/_template` and a fake `profiles/lab`, plus `machines/_template.toml`.
- **Lint** (`lint/lint.py`): fails if an identifier from a profile denylist appears under `core/`.
- **CLAUDE.md check** (`analyzer-action/`): a GitHub Action that counts the rules in your CLAUDE.md and shows which ones a hook can enforce. Add it to a workflow with one step. See `analyzer-action/README.md`.

## The pro kit

The paid tier adds a renderer that merges the whole kit into a live `settings.json` without losing your hooks (with manifest and uninstall), a doctor that proves each gate denies a bad input under an isolated home, and a local search tool for your notes. Scheduled watchers that carry their own stop condition are planned. Get it at https://ko-fi.com/s/204b3de50e.

## Authorship

Built by an engineer and his Claude Code sessions. The sessions wrote and maintain this repo; the engineer sets the direction, reviews the results and decides what ships. Expect rough edges that come from that: the hooks are tested by smoke runs rather than a full suite, and the rules reflect one person's working style.

## License

MIT. See `LICENSE`.

## Limitations

**Platform metadata is outside the lint.** The lint reads file contents. It cannot see what the hosting platform publishes about the account that acts: the push actor in GitHub's Activity view, the repository creator, the organization owner, the email on a commit. When this repo first went up, every file was clean and the Activity view still showed the owner's personal account as the pusher. The fix was mechanical, not a rule: the repo was deleted and re-created, and every push now comes from a GitHub App bot owned by the organization. Before calling anything public clean, list what the platform publishes about the actor and check each item without being logged in.
