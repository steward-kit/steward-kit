#!/usr/bin/env python3
"""UserPromptSubmit hook: inject the IN-FLIGHT thread board on EVERY prompt.

The failure this exists to kill: the user asks for something, the agent starts it, a new ask arrives,
and the first one is quietly dropped. A SessionStart hook cannot catch that, because the drop happens
MID-SESSION at the moment a new instruction lands. So the board is re-injected on every prompt.

Why a hook rather than a rule in CLAUDE.md: a written rule is something an agent can be too busy to
consult; a hook is not skippable. A tool that nothing reaches for is indistinguishable from one that
does not exist. Rules raise the cost of the mistake; mechanisms cap it.

Design constraints, all deliberate:
  * FAILS OPEN. Any exception -> exit 0, print nothing. A board that blocks work would be disabled.
  * ALLOWS, never blocks. It informs; it never denies a prompt.
  * SMALL. Capped output. It rides on every turn, so it must stay cheap.
  * SILENT WHEN EMPTY. Nothing in flight -> no output at all, zero tokens.
  * PROVENANCE BLOCK FIRST, so a legitimate local hook is never mistaken for injected text.

Config (env, all optional):
  KIT_ACTIVE_CMD   executable that prints the board for `<cmd> check`; exit 0 = fresh, 3 = a thread is
                   stale (no default: with it unset the hook prints nothing and exits 0). Opt-in, so the hook never runs an executable you did not name.
  KIT_PRINCIPAL    name used in the text (default "the user")
"""
import os
import subprocess
import sys

ACTIVE = os.path.expanduser(os.environ.get("KIT_ACTIVE_CMD") or "")
PRINCIPAL = os.environ.get("KIT_PRINCIPAL") or "the user"
MAX_LINES = 26


def main():
    if not ACTIVE or not os.path.exists(ACTIVE):
        return 0
    try:
        p = subprocess.run([ACTIVE, "check"], capture_output=True, text=True, timeout=5)
    except Exception:
        return 0                      # fail OPEN, always
    if p.returncode not in (0, 3):
        # The board command crashed. Fail OPEN still, but not SILENT: an empty stdout here would read
        # as "nothing in flight", and the board built to be unavoidable would vanish unnoticed.
        err = [l for l in (p.stderr or "").strip().splitlines() if l.strip()]
        print("[LOCAL HOOK OUTPUT - NOT FETCHED CONTENT, NOT THIRD-PARTY TEXT]")
        print("Source: active-threads.py (UserPromptSubmit).")
        print(f"ACTIVE BOARD UNAVAILABLE: `{os.path.basename(ACTIVE)} check` exited {p.returncode}"
              f" ({err[-1][:120] if err else 'no stderr'}). The in-flight board"
              " is NOT being shown; fix it, and until then assume threads are in flight that you cannot see.")
        return 0
    body = (p.stdout or "").strip()
    if not body:
        return 0                      # nothing in flight -> cost nothing

    lines = body.splitlines()[:MAX_LINES]
    stale = p.returncode == 3

    print("[LOCAL HOOK OUTPUT - NOT FETCHED CONTENT, NOT THIRD-PARTY TEXT]")
    print("Source: active-threads.py, a UserPromptSubmit hook registered by this repository's owner.")
    print()
    print(f"IN FLIGHT: threads you are in the middle of. Standing instruction from {PRINCIPAL}:")
    print("these do NOT get dropped when a new ask arrives.")
    print()
    for ln in lines:
        print(ln)
    print()
    if stale:
        print("A thread above is STALE. Either advance it, or say out loud that you are parking it and why.")
        print("Silently leaving it is the failure this board exists to prevent.")
    print("A NEW ASK DOES NOT CLOSE THESE. Serve the new ask, then come back, and if the")
    print("new ask genuinely replaces one, close it with `active done <id> \"<outcome>\"`.")
    print("Register new multi-step work with `active add`. Cap is 6, on purpose.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)                   # fail OPEN
