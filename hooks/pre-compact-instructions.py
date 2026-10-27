#!/usr/bin/env python3
"""PreCompact hook — supplies custom instructions to EVERY compaction.

PROVENANCE: see the PROVENANCE constant below -- it is EMITTED to stdout, ahead of the
instructions. It must never live only in this docstring: the summariser never sees the
docstring, and an unattributed wall of imperatives arriving inside a summarisation prompt
is indistinguishable from a prompt injection. Measured 2026-08-20: it was refused as one.

MECHANISM (verified in CLI bundle 2.1.235 by two independent agents, 2026-08-20):
  A PreCompact hook supplies compaction instructions by printing PLAIN TRIMMED TEXT
  to stdout, exit 0, not blocked. NOT via hookSpecificOutput.additionalContext and
  NOT via a customInstructions JSON key -- neither co-occurs with PreCompact anywhere
  in the bundle. J1e() joins the stdout of every successful hook into
  `newCustomInstructions`; Ggi() then appends it verbatim to the summarizer prompt
  under a literal "Additional Instructions:" heading. This runs on the AUTOMATIC
  (trigger:"auto") path -- reactive AND precomputed -- not just manual /compact.

FAIL-OPEN BY CONSTRUCTION: every path exits 0. A hook that raised would risk blocking
compaction near the context ceiling, which is strictly worse than a generic summary.
Keep the emitted text under ~4000 chars: no truncation was found on this path, but
absence of evidence is not evidence of absence.
"""
import os
import sys

# Config (env, all optional): KIT_KB_ROOT (default ~/kb), KIT_TODO_FILE (default TODO.md), KIT_LOG_DIR (default ~/.claude)
KB = os.path.expanduser(os.environ.get("KIT_KB_ROOT") or "~/kb")
TODO_NAME = os.environ.get("KIT_TODO_FILE") or "TODO.md"
STATE_DIR = os.path.expanduser(os.environ.get("KIT_LOG_DIR") or "~/.claude")

PROVENANCE = """\
[LOCAL HOOK OUTPUT - NOT FETCHED CONTENT, NOT THIRD-PARTY TEXT]

Source: pre-compact-instructions.py - a PreCompact
hook registered by this repository's owner in its own settings.json. The CLI
executed it locally on this machine and the harness delivered its stdout to you directly.
It did not arrive from a web page, a tool result, a file written by a third party, or any
network source. You can verify this by reading that file.

SCOPE: these are the repository owner's standing preferences for how THEIR OWN sessions get
summarised. They govern only the SHAPE of the summary you are already writing - which
details to keep and which to drop. They do not ask you to take any action outside
producing this summary, do not ask you to fetch or open anything, and do not redefine
your instructions. Following them IS the summarisation task.

"""

BASE = """\
PRESERVE, VERBATIM WHERE SHORT ENOUGH:

1. CORRECTIONS OVER CONCLUSIONS. For anything gotten wrong this session: what was
   believed, what was actually true, and what changed my mind. Conclusions can be
   recomputed from the KB; a corrected instinct cannot be recovered once the
   conversation is gone. This outranks everything else here.

2. THE USER'S OWN WORDS. Any instruction, ruling, correction, veto or preference they
   stated - quoted exactly, with the date. Never paraphrase them into first person.
   If the exact words are already gone, label it "paraphrase" explicitly.

3. WHAT IS NOT YET ON DISK. Findings, decisions and measurements made this session
   that have not been written to the status file, the TODO file, the history file or a topic
   file. Name each and where it belongs. Highest-risk category: everything else has
   a durable copy.

4. OPEN THREADS WITH THEIR EXACT NEXT ACTION. For each: what is blocked, on whom or
   what, and the single next command or decision. A thread without its next action
   has not been preserved.

5. IN-FLIGHT WORK. Any sub-agent or workflow dispatched and not yet returned: what
   it was asked, which model, what its output feeds.

6. IRREVERSIBLE-ACTION STATE. Any command shown to the user awaiting a yes; any approval granted,
   used or expired.

7. MEASUREMENTS WITH THEIR NUMBERS. VRAM figures, token counts, timings, file sizes,
   exit codes. A measurement without its number is an opinion.

8. FAILED APPROACHES AND WHY, so the next context does not retry them.

DISCARD FREELY: tool-call mechanics and their output; file contents already on disk;
exploratory reads that led nowhere; restatements of what the user said; step-by-step
narration. For anything already written into the KB, say WHERE it was written
instead of repeating it.

NEVER include a secret value in the summary - keys, tokens, passwords, private keys.
Secret values must never appear in session output. Refer to a location,
never a value.

DO NOT SOFTEN OR SUMMARISE AWAY A FAILURE, A WRONG PREDICTION, OR A "DON'T KNOW".
A "don't know" flattened into a "no" is the single most damaging thing this summary
can do."""

AUTO_EXTRA = """

This compaction fired automatically, so the session did not choose its moment: work
may be mid-flight. Record explicitly what was in progress and what it was waiting on."""


def gauges(transcript_path):
    """2026-10-17: three FILLED-IN gauges for the handoff. Two are measured here
    (a measured number beats a rule to remember); the third is a blank the summary must fill.
    Fails open: any error yields '?' for that gauge, never an exception."""
    br, todo = "?", "?"
    cap = "?"
    try:
        import json as _j
        cap = str(_j.load(open(os.path.join(KB, ".claude", "kb-caps.json"))).get(TODO_NAME, "?"))
    except Exception:
        pass
    try:
        todo = str(os.path.getsize(os.path.join(KB, TODO_NAME)))
    except Exception:
        pass
    try:
        import json
        n_tool = n_batch = 0
        seen = {}
        for line in open(transcript_path, errors="replace"):
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get("type") != "assistant" or o.get("isSidechain"):
                continue
            m = o.get("message") or {}
            k = m.get("id") or o.get("uuid")
            seen[k] = seen.get(k, 0) + sum(1 for b in (m.get("content") or []) if isinstance(b, dict) and b.get("type") == "tool_use")
        for c in seen.values():
            if c:
                n_tool += 1
                n_batch += c >= 2
        if n_tool:
            br = "%d%% (%d of %d tool-using turns carried 2+ calls)" % (round(100 * n_batch / n_tool), n_batch, n_tool)
    except Exception:
        pass
    return (
        "\n\n9. THREE GAUGES - copy these three lines into the summary, filled in. A blank that must be\n"
        "   FILLED beats a rule to remember.\n"
        "   batch rate this session: %s\n"
        "   TODO bytes: %s (cap %s)\n"
        "   prior art consulted: [YOU fill this: the KB files / your search tool's hits read BEFORE building anything\n"
        "   new this session; write 'none' if none, never leave it blank]" % (br, todo, cap))


def main() -> int:
    trigger = ""
    tpath = ""
    try:
        import json
        raw = sys.stdin.read()
        if raw.strip():
            pl = json.loads(raw)
            trigger = str(pl.get("trigger", "") or "")
            tpath = str(pl.get("transcript_path", "") or "")
    except Exception:
        trigger = ""          # unreadable stdin must not cost us the instructions
    try:
        extra = gauges(tpath) if tpath else gauges("/nonexistent")
    except Exception:
        extra = ""
    out = PROVENANCE + BASE + extra + (AUTO_EXTRA if trigger == "auto" else "")
    # Sentinel: a hook that never records firing is indistinguishable from one that
    # never fires. Best-effort only -- must never affect stdout or the exit code.
    try:
        import datetime
        with open(os.path.join(STATE_DIR, "precompact-fired.log"), "a") as fh:
            fh.write("%s trigger=%s bytes=%d\n" % (
                datetime.datetime.now().isoformat(timespec="seconds"), trigger or "?", len(out)))
    except Exception:
        pass
    sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Absolute backstop: emit the base text and never fail.
        try:
            sys.stdout.write(PROVENANCE + BASE)
        except Exception:
            pass
        sys.exit(0)
