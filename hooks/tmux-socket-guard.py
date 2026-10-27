#!/usr/bin/env python3
"""tmux-socket-guard.py: PreToolUse(Bash) hook. Denies a tmux server kill that names no socket.

Why: a workflow agent testing something set TMUX_TMPDIR to a scratch directory and then killed the
tmux server, from inside a pane of the REAL tmux server. When $TMUX is set, tmux uses the socket named
in $TMUX and ignores TMUX_TMPDIR, so it killed the real server and every live Claude session in it.
Its earlier test run had `unset TMUX` and was harmless; this one did not.

Rule: a server kill must name its socket explicitly (-L <name> or -S <path>). Those flags win over
$TMUX, so the target is the one written on the command line.
Fails OPEN on anything it cannot parse (a guard that blocks correct work gets disabled).
Known limit: it splits the command text on ; & | and newlines, so a heredoc body that happens to
contain a line starting with the bare kill command is also denied.
"""
import json
import re
import sys

try:
    data = json.load(sys.stdin)
    cmd = (data.get("tool_input") or {}).get("command") or ""
except Exception:
    sys.exit(0)

bad = []
# Each simple command: split on ; && || | & and newlines.
for seg in re.split(r"[;&|\n]+", cmd):
    # tmux must be the command itself (after optional VAR=x / sudo / env), not a word in a quoted message
    m = re.match(r"\s*(?:\w+=\S*\s+)*(?:sudo\s+|env\s+(?:-\S+\s+|\w+=\S*\s+)*)?(?:\S*/)?tmux(\s.*)?$", seg)
    if not m:
        continue
    args = m.group(1) or ""
    if not re.search(r"(?:^|\s)kill-server(?:\s|$)", args):
        continue
    if re.search(r"(?:^|\s)-[a-zA-Z]*[LS]", args):
        continue
    bad.append(seg.strip())

if bad:
    reason = (
        "[LOCAL HOOK tmux-socket-guard.py] DENIED: a tmux kill-server with no "
        "-L/-S. Inside a tmux pane, $TMUX overrides TMUX_TMPDIR, so this kills the REAL tmux "
        "server and every live Claude session on the machine. "
        "Name the socket: `tmux -L <test-name> kill-server` (use the same -L for the test "
        "server's other tmux calls). Killing the real server is the owner's call, never a test step. "
        f"Offending: {bad[0][:200]}"
    )
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason}}))
sys.exit(0)
