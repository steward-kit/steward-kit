# Hooks pack

Twelve Claude Code hooks, each one a single Python 3 file with no dependencies beyond the standard library. Every hook reads its event JSON on stdin, fails open (any error of its own means exit 0 and no output) and takes its paths and names from environment variables with a documented default. Nothing here knows about any particular machine or person.

Hooks that block (kb-size-gate, tier-guard, tmux-socket-guard) say so in their denial text. vc-guard flags after the write and cannot undo it. The rest only nudge, and a nudge can be ignored by the model; the log each one writes is the durable trace.

## What each hook enforces, and why

**kb-size-gate.py** (PreToolUse: Write, Edit, MultiEdit, Bash). A file listed in `kb-caps.json` may not grow past its byte cap. Shrinking and same-size edits always pass, so pruning is never blocked. For Bash it parses the command with a quote-aware lexer to find real writes (redirects, tee, sed -i, cp, mv, python with -c and so on) instead of matching words, because the first naive version denied `grep -n install TODO.md`. Why: a hot status file that only grows ends up bigger than the model can read in one call, and the next session reads past dead history to find live work.

**tier-guard.py** (PreToolUse: Agent, Workflow). Denies an agent spawn that does not choose a model, and one that does not choose an effort, unless the agent definition pins it. For Workflow scripts it checks each `agent()` call for a top-level `model` and `effort` key. Why: built-in agent types silently inherit the session's most expensive model, so a cheap job costs top-tier money unless someone decides otherwise on purpose.

**tmux-socket-guard.py** (PreToolUse: Bash). Denies a tmux server kill that names no socket with -L or -S. Why: inside a tmux pane, `$TMUX` overrides `TMUX_TMPDIR`, so a test that thought it was killing a scratch server killed the real one and every live session in it.

**vc-guard.py** (PostToolUse: Write, Edit, NotebookEdit). Flags (PostToolUse exit 2 reports after the write; it does not block) when a file was written outside any git work tree and outside the exempt prefixes. Why: work that lives in no repository has no history and no backup path. It looks only for a `.git` ancestor, makes no subprocess call, and refuses exempt prefixes broad enough to switch the guard off (an empty prefix, `/`, your home directory or any ancestor of it).

**correction-catcher.py** (UserPromptSubmit). When the prompt matches a correction phrase ("that's not what I asked", "you forgot"), reminds the agent to park the correction itself: what it believed, what was true, what changed its mind. Why: a conclusion can be recomputed later, a corrected instinct cannot be recovered once the conversation is gone. Machine-generated turns are skipped.

**active-threads.py** (UserPromptSubmit). Prints the board of in-flight threads on every prompt, from a command you provide (`KIT_ACTIVE_CMD check`); off until you set it. Silent when the board is empty, loud when the command itself crashes. Why: the usual way an agent drops a task is mid-session, at the moment a new ask arrives, which a session-start hook cannot catch.

**unwritten-fact-nudge.py** (Stop). If the last user message looks like it carried a fact or a decision (first-person state phrases, or a date or amount stated flatly) and the turn made no write to a KB path, prints one nudge. Why: facts told to an agent and never written down are lost at the next clear. It is a regex and fails both ways; the rule belongs in your own CLAUDE.md, the hook only reminds.

**dated-commit-nudge.py** (Stop). If the turn wrote a future date near a commitment word (due, court, appointment, interview) into the KB, and the scheduling command did not run and the ledger has no row for that date, prints one nudge. Why: a date written down as prose is not a reminder. The scheduling command and the ledger format are yours to supply; see the header of the file.

**tiering-score.py** (Stop). Scores each session from its transcript (tool calls, spawns, spawns with a chosen tier, batch rate, first-turn context size) and logs one row. Optionally runs an alert command, at most once a day, when a top-tier session did 80 or more serial tool calls alone. Why: a rule about delegation is only credible if someone can measure it. It parses in a detached child so Stop returns at once.

**session-prompt-log.py** (SessionStart). Logs the size of everything a session starts with (CLAUDE.md, the shared contract, the memory index, the biggest sections, the hot KB files). Prints nothing. Why: context cost is set at session start, and you cannot trim what you never measured.

**pre-compact-instructions.py** (PreCompact). Prints standing instructions for the compaction summary: keep corrections over conclusions, keep the user's exact words, name what is not yet on disk, keep every open thread with its next action, never include a secret, never soften a "don't know" into a "no". It also fills in three gauges (batch rate, TODO size against its cap, prior art consulted). The text opens with a provenance block because an unattributed list of imperatives inside a summarisation prompt looks like an injection, and was refused as one in testing.

**warm-start.py** (SessionStart). After `/clear`, injects the RESUME HERE block of your status file and the head of your TODO file into the fresh context. Optionally, when you arm a flag file by hand, types a resume message into its own tmux pane. That half is off by default, is consumed at each clear, stops after `KIT_MAX_CYCLES` unattended resumes, fails closed on a bad counter, and sends nothing unless `KIT_PANE_GATE` names an executable that reports the pane ready. If no RESUME HERE heading matches it says so loudly instead of printing a line that looks like a healthy empty state.

## Configuration

All variables are optional.

| Variable | Default | Used by |
| --- | --- | --- |
| `KIT_KB_ROOT` | `~/kb` | kb-size-gate, session-prompt-log, pre-compact-instructions, warm-start |
| `KIT_KB_ROOTS` | `~/kb` | unwritten-fact-nudge, dated-commit-nudge (colon-separated) |
| `KB_GATE_ROOT`, `KB_GATE_CAPS`, `KB_GATE_STATE` | KB root, `<root>/.claude/kb-caps.json`, `~/.local/state/kb-gate` | kb-size-gate |
| `KIT_LOG_DIR` | `~/.claude/logs` | session-prompt-log, unwritten-fact-nudge, dated-commit-nudge, tiering-score, pre-compact-instructions (`~/.claude`) |
| `KIT_STATE_DIR` | `~/.claude` | warm-start |
| `KIT_STATUS_FILE`, `KIT_TODO_FILE` | `STATUS.md`, `TODO.md` | warm-start, pre-compact-instructions |
| `KIT_KB_FILES` | `TODO.md,STATUS.md` | session-prompt-log |
| `KIT_KB_WRITE_TOOLS` | none (comma list of your KB write commands) | unwritten-fact-nudge |
| `KIT_RELAY_PREFIX_RE` | none | unwritten-fact-nudge |
| `KIT_COMMIT_CMD`, `KIT_COMMIT_LEDGER` | `commit-date`, `<kb root>/state/commitments.jsonl` | dated-commit-nudge |
| `KIT_ACTIVE_CMD` | none (hook is off until set) | active-threads |
| `KIT_ALERT_CMD`, `KIT_SPAWN_AGENTS` | none, `scout,worker` | tiering-score |
| `KIT_CONTRACT_FILE` | `~/.claude/contract.md` | session-prompt-log |
| `KIT_VC_EXEMPT`, `VC_CONF_DIR`, `KIT_VC_ADOPT_CMD` | none, `~/.config/kit-vc`, `git init` | vc-guard |
| `KIT_TIER_ROUTE` | short generic hint | tier-guard |
| `KIT_MAX_CYCLES`, `KIT_PANE_GATE` | `3`, none | warm-start |
| `KIT_PRINCIPAL` | `the user` | most nudges |
| `KIT_CORRECTION_TOOL` | `one line in the topic file` | correction-catcher: how the nudge says to park a correction |
| `UFN_LOG` | `<KIT_LOG_DIR>/unwritten-fact-nudge.log` | unwritten-fact-nudge: log file path |
| `DCN_LEDGER` | `<kb root>/state/commitments.jsonl` | dated-commit-nudge: older alias of `KIT_COMMIT_LEDGER` |
| `DCN_LOG` | `<KIT_LOG_DIR>/dated-commit-nudge.log` | dated-commit-nudge: log file path |
| `DCN_TODAY` | today | dated-commit-nudge: ISO date to treat as today (for tests) |
| `TIERING_SCORE_DRYRUN` | unset | tiering-score: `1` never runs the alert command |
| `TIERING_SCORE_SYNC` | unset | tiering-score: `1` parses in the foreground instead of a detached child |

## Install

    mkdir -p ~/.claude/hooks && cp hooks/*.py ~/.claude/hooks/
    mkdir -p ~/kb/.claude && cp hooks/examples/kb-caps.json ~/kb/.claude/kb-caps.json

Then merge `hooks/examples/settings-snippet.json` into the `hooks` object of `~/.claude/settings.json`, keeping any hooks you already have. The snippet registers all twelve; delete the entries you do not want.

The kb-size-gate override is a one-shot token file, `~/.local/state/kb-gate/override-<session_id>.json`, holding `{"reason": "...", "expires": <epoch seconds>}`. The next refusal for that session consumes it and logs the use. Write it with your own helper or by hand.

## Known limits

- Tested on Linux. macOS should work. Windows: the hooks that use tmux, fcntl or fork exit quietly.
- Run `python3 -m py_compile` on each file after you edit it. The files are tested by smoke runs, not by a test suite.
- tmux-socket-guard splits the command text on `;`, `&`, `|` and newlines, so a heredoc body with a line that starts with the bare kill command is also denied.
- The nudge hooks are regexes. They miss real facts and flag chatter. Treat their logs as the measurement.
- Hook behavior was observed on Claude Code 2.1.x. Re-check after an upgrade: a guard keyed to today's behavior can stop matching without any error.
