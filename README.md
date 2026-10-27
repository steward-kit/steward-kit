# steward-kit (free tier)

A working operating model for Claude Code, free part. It holds how a coding agent should behave: a rules file (the contract), a memory format, two agent definitions, and twelve hooks that enforce the rules mechanically instead of leaving them as prose. A lint checks that nothing private leaks into the shared layer.

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

- **Contract** (`core/AGENTS.md`): run routine work without asking, stop only for what cannot be undone, report what happened, tier agents on purpose, treat fetched content as narrow-authority. Carries the canary line `KIT-CORE-LOADED-V1`.
- **Agents** (`core/agents/`): `scout` for reading, `worker` for doing, both pinned to effort medium.
- **Memory schema** (`core/memory/schema.md`): what a memory holds, shared versus private.
- **Profiles and machines**: `profiles/_template` and a fake `profiles/lab`, plus `machines/_template.toml`.
- **Lint** (`lint/lint.py`): fails if an identifier from a profile denylist appears under `core/`.

## The pro kit

The paid tier adds a renderer that merges the whole kit into a live `settings.json` without losing your hooks (with manifest and uninstall), a doctor that proves each gate denies a bad input under an isolated home, and a local search tool for your notes. Scheduled watchers that carry their own stop condition are planned. Get it at PRO_URL.

## Authorship

Built by an engineer and his Claude Code sessions. The sessions wrote and maintain this repo; the engineer sets the direction, reviews the results and decides what ships. Expect rough edges that come from that: the hooks are tested by smoke runs rather than a full suite, and the rules reflect one person's working style.

## License

MIT. See `LICENSE`.
