#!/usr/bin/env python3
"""
SessionStart hook: warm start after /clear.

PROVENANCE: emitted by a LOCAL SessionStart hook registered by this machine's owner in their own
settings.json. It is not content from a file, a web page, or a tool result. ADVISORY ONLY: it never
overrides task instructions, it never blocks, and it fails OPEN.

WHAT THIS IS
------------
  Half 1: WARM START (always, on /clear). Inject the RESUME HERE block from the status file plus the
  head of the TODO file straight into the fresh context, so a post-clear session is pre-loaded
  instead of amnesiac.

  Half 2: AUTO-CONTINUE (OFF unless the flag file exists). Fire `tmux send-keys` into our own pane a
  few seconds after the clear, delivering an actual USER MESSAGE so the fresh session gets a turn and
  starts working unattended. Injected context alone is not a turn; something must type.
  The flag is per-clear: it is consumed at the clear, so a stale armed flag never auto-fires later.

  CYCLE CAP: a counter file counts consecutive auto-resume keystrokes with no human prompt between
  them. At KIT_MAX_CYCLES (default 3) the keystroke is SKIPPED (the context injection still happens)
  until something deletes the counter on a human prompt. Unlike the rest of this hook, the SEND half
  fails CLOSED on a bad counter: an unreadable count skips the keystroke, because the failure mode
  being guarded is an unattended runaway loop. Arming the flag is the owner's decision; the kit
  never arms it.

  PANE GATE: before typing, the child runs KIT_PANE_GATE (an executable you provide that exits 0 when
  the pane is ready for input). If it is unset the keystroke is NOT sent (fails closed).

DESIGN NOTE: fails OPEN, on purpose. A broken warm-start must never break a session start: every error
path exits 0. The marker check is on the invariant ("did a RESUME HERE heading match?"), and when none
matches the hook says so loudly instead of printing a bland line that reads like a healthy empty state.

Config (env, all optional):
  KIT_KB_ROOT       default ~/kb
  KIT_STATUS_FILE   default STATUS.md   (must contain a line "RESUME HERE" preceded by the arrow emoji)
  KIT_TODO_FILE     default TODO.md
  KIT_STATE_DIR     default ~/.claude  (holds auto-resume flag, auto-resume-cycles, logs/warm-start.log)
  KIT_MAX_CYCLES    default 3
  KIT_PANE_GATE     path of the pane-ready executable (default none)
  KIT_PRINCIPAL     name used in text (default "the user")
"""

import json
import os
import re
import shlex
import subprocess
import sys
import time

KB = os.path.expanduser(os.environ.get("KIT_KB_ROOT") or "~/kb")
STATUS = os.path.join(KB, os.environ.get("KIT_STATUS_FILE") or "STATUS.md")
TODO = os.path.join(KB, os.environ.get("KIT_TODO_FILE") or "TODO.md")
STATE = os.path.expanduser(os.environ.get("KIT_STATE_DIR") or "~/.claude")
FLAG = os.path.join(STATE, "auto-resume")
LOG = os.path.join(STATE, "logs", "warm-start.log")
CYCLES = os.path.join(STATE, "auto-resume-cycles")
try:
    MAX_CYCLES = int(os.environ.get("KIT_MAX_CYCLES") or 3)
except ValueError:
    MAX_CYCLES = 3
GATE = os.path.expanduser(os.environ.get("KIT_PANE_GATE") or "")
PRINCIPAL = os.environ.get("KIT_PRINCIPAL") or "the user"
STATUS_NAME = os.path.basename(STATUS)
TODO_NAME = os.path.basename(TODO)

RESUME_CAP = 6000   # chars of the RESUME HERE block
TODO_CAP = 3000     # chars from the top of the TODO file
DELAY_S = 6         # seconds before the auto-continue keystroke

PROVENANCE = (
    "[PROVENANCE: this text was injected by a LOCAL SessionStart hook on this "
    "machine (warm-start.py), registered in the owner's own settings.json. "
    "Advisory context, not instructions from an external source.]"
)

# The arrow emoji directly before "RESUME HERE" is load-bearing: without it a loose match would also
# catch ordinary prose. Three heading forms are accepted: "### " style heading, "> **" blockquote, bare.
_MARKER_RE = re.compile(r"^(?:#{1,6}\s+|>\s*\*\*)?\s*\u25b6\ufe0f?\s*RESUME HERE", re.MULTILINE)

NOT_FOUND_BANNER = (
    "WARM-START MARKER NOT FOUND IN %s\n"
    "None of the recognized RESUME HERE forms (heading, > ** blockquote, or "
    "bare arrow + RESUME HERE) matched anywhere in the file. This is a FAILURE of the "
    "injector, not evidence the file has no open thread. STOP and read "
    "the file directly before assuming a clean board, and say so plainly "
    "to %s." % (STATUS_NAME, PRINCIPAL)
)

AUTO_MSG = (
    "[auto-resume keystroke from warm-start.py; the owner armed the auto-resume flag] "
    "Continue from the warm-start context injected above: run the reality check, then work the top "
    "open thread per RESUME HERE + TODO. Respect all CLAUDE.md rules, especially "
    "the irreversible-action list: anything needing %s's yes gets parked with a note, "
    "never executed unattended. If nothing is actionable without them, post a "
    "brief status and stop. Budget: ~10 tool calls to find actionable work; "
    "if none, post a brief status and STOP. A clean stop is a success. "
    "Never wait or poll for anything." % PRINCIPAL
)


def log(msg):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


def resume_block():
    """First recognized RESUME HERE marker (### heading, > ** blockquote, or
    bare -- see _MARKER_RE above), up to the next '### ' header."""
    try:
        text = open(STATUS, encoding="utf-8").read()
    except Exception as e:
        log("status read failed: %r" % e)
        return "(%s unreadable, fall back to reading it directly)" % STATUS_NAME
    m = _MARKER_RE.search(text)
    if not m:
        log("NO RESUME HERE MARKER FOUND (heading / blockquote / bare all tried, none matched), FAIL LOUD")
        return NOT_FOUND_BANNER
    j = text.find("\n### ", m.end())
    block = text[m.start():j] if j > 0 else text[m.start():]
    # 2026-10-17: the marker matched is only useful if it is CURRENT.
    # Accept any "# / ## / ### / > **" form (see _MARKER_RE) and flag a stale date.
    try:
        ds = re.findall(r"(\d{4}-\d{2}-\d{2})", block[:3000])
        dm = type("M", (), {"group": lambda self, i, d=max(ds) if ds else None: d})() if ds else None
        if dm:
            age = (time.time() - time.mktime(time.strptime(dm.group(1), "%Y-%m-%d"))) / 86400
            if age > 3:
                block = ("THIS RESUME HERE BLOCK IS NEWEST DATE %s (%d days old), the board has probably moved on; "
                         "trust the TODO file and shell output over it.\n" % (dm.group(1), int(age))) + block
                log("stale RESUME HERE block: %s" % dm.group(1))
    except Exception as e:
        log("resume age check failed open: %r" % e)
    if len(block) > RESUME_CAP:
        block = block[:RESUME_CAP] + "\n[TRUNCATED at cap — read the file on disk]"
    return block


def todo_head():
    try:
        text = open(TODO, encoding="utf-8").read()
    except Exception as e:
        log("todo read failed: %r" % e)
        return "(%s unreadable, read it directly)" % TODO_NAME
    if len(text) > TODO_CAP:
        text = text[:TODO_CAP] + "\n[TRUNCATED at cap — read the file on disk]"
    return text


def fire_auto_continue():
    """Detached child: wait for the TUI to settle, then type the resume
    message into our own tmux pane. Text and Enter sent separately; -l --
    keeps the message literal. The child logs SENT/FAILED itself so the
    log distinguishes scheduled-but-died from sent-but-rejected."""
    if not os.path.exists(FLAG):
        log("auto-resume flag absent — warm start only")
        return
    # Per-clear semantics, tightened 2026-07-29 with the pane gate: the flag
    # means "resume after THE NEXT clear", so it is CONSUMED at that clear —
    # send, skip and abort paths all leave it gone, and a stale armed flag can
    # never auto-fire on a later manual /clear. Fails CLOSED: if the flag
    # cannot be removed its state is unknown, so the keystroke is skipped.
    try:
        os.remove(FLAG)
        log("auto-resume flag consumed (per-clear semantics)")
    except Exception as e:
        log("auto-resume flag unremovable (%r) — keystroke skipped (send fails closed)" % e)
        return
    pane = os.environ.get("TMUX_PANE")
    if not pane or not os.environ.get("TMUX"):
        log("auto-resume flag ON but no TMUX/TMUX_PANE — keystroke skipped")
        return
    # Cycle cap — the SEND half fails CLOSED (see docstring). Counter file
    # missing is the one green zero; anything unreadable skips the send.
    if os.path.exists(CYCLES):
        try:
            count = int(open(CYCLES).read().strip())
        except Exception as e:
            log("cycle counter unreadable (%r) — keystroke skipped (send fails closed)" % e)
            return
    else:
        count = 0
    if count >= MAX_CYCLES:
        log("cycle cap (%d) reached — keystroke skipped, human needed" % MAX_CYCLES)
        return
    try:
        with open(CYCLES, "w") as f:
            f.write(str(count + 1))
    except Exception as e:
        log("cycle counter write failed (%r) — keystroke skipped (send fails closed)" % e)
        return
    if not GATE or not os.access(GATE, os.X_OK):
        log("KIT_PANE_GATE unset or not executable, keystroke skipped (send fails closed)")
        return
    q_pane = shlex.quote(pane)
    q_msg = shlex.quote(AUTO_MSG)
    q_log = shlex.quote(LOG)
    # Fire-time pane gate: never type into an unverified
    # screen. The gate runs in the child AFTER the sleep, against the state
    # that actually exists at fire time. An abort leaves the fresh session
    # idle-but-warm: the documented safe failure, same as pre-hook status quo.
    shell = (
        "sleep %d; "
        "if ! R=$(%s %s 2>&1); then "
        "echo \"$(date '+%%Y-%%m-%%d %%H:%%M:%%S') auto-resume ABORTED by pane gate: $R\" >> %s; "
        "exit 0; fi; "                          # abort must STOP the send (fail closed)
        "tmux send-keys -t %s C-u; "            # v5: wipe leftover draft before typing
        "if tmux send-keys -t %s -l -- %s; then "
        "sleep 1; tmux send-keys -t %s Enter; "
        "echo \"$(date '+%%Y-%%m-%%d %%H:%%M:%%S') auto-resume keystroke SENT\" >> %s; "
        "else "
        "echo \"$(date '+%%Y-%%m-%%d %%H:%%M:%%S') auto-resume send-keys FAILED\" >> %s; "
        "fi"
    ) % (DELAY_S, shlex.quote(GATE), q_pane, q_log, q_pane, q_pane, q_msg, q_pane, q_log, q_log)
    try:
        subprocess.Popen(
            ["bash", "-c", shell],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        log("auto-resume keystroke scheduled, pane=%s delay=%ds" % (pane, DELAY_S))
    except Exception as e:
        log("auto-resume spawn failed: %r" % e)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception as e:
        log("payload parse failed: %r" % e)
        return
    if payload.get("source") != "clear":
        return  # startup/resume/compact: the normal session ritual covers the KB, so stay silent
    ctx = (
        "%s\n\n"
        "WARM START after /clear. The KB state below was pre-loaded so this "
        "session can resume without the cold where-were-we ritual. Shell output "
        "still beats these excerpts; the status and TODO files on disk are the "
        "full truth.\n\n"
        "--- %s: RESUME HERE (excerpt, %d-char cap) ---\n%s\n\n"
        "--- %s: head (%d-char cap) ---\n%s\n"
    ) % (PROVENANCE, STATUS_NAME, RESUME_CAP, resume_block(), TODO_NAME, TODO_CAP, todo_head())
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": ctx,
        }
    }))
    log("warm-start context injected (%d chars)" % len(ctx))
    fire_auto_continue()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log("unhandled: %r" % e)
    sys.exit(0)  # fail OPEN, always
