#!/usr/bin/env python3
"""UserPromptSubmit hook: correction-catcher.

ADVISORY ONLY. Never blocks, fails open, silent unless a clear correction phrase matches.

Why: a correction is the first thing lost when the conversation ends. When the user says
"that's not what I asked", the agent should write down the wrong assumption, the evidence and the fix, before it carries on. A regex with no model call costs nothing per prompt.
Machine-generated turns (continuation summaries, notifications, other hooks' output) are skipped
on purpose: a quoted correction inside a summary is not a new correction.

Config (env, all optional):
  KIT_PRINCIPAL        name used in the nudge text (default "the user")
  KIT_CORRECTION_TOOL  how to park a correction (default "one line in the topic file")
"""
import json
import os
import re
import sys

PRINCIPAL = os.environ.get("KIT_PRINCIPAL") or "the user"
PARK_HOW = os.environ.get("KIT_CORRECTION_TOOL") or "one line in the topic file"

SKIP = ("This session is being continued", "Another Claude session", "[Workflow",
        "<task-notification", "[SYSTEM NOTIFICATION", "<system-reminder", "[LOCAL HOOK")
RE = re.compile(
    r"\b(that'?s not (right|what|true|correct|how)|that is not (right|what|true|correct)|"
    r"that'?s wrong|you'?re wrong|you are wrong|you got (it|that) wrong|"
    r"not what i (asked|said|meant|wanted)|i (already )?told you|i never (said|asked)|"
    r"you (missed|forgot|ignored|skipped) (the|that|it|my|what)|stop (doing|using) that|"
    r"don'?t (ever )?do that again|that'?s not what)\b",
    re.I,
)

try:
    prompt = (json.load(sys.stdin).get("prompt") or "").strip()
    if prompt.startswith(SKIP):
        sys.exit(0)
    m = RE.search(prompt[:1500])
    if not m:
        sys.exit(0)
    print(
        "[LOCAL HOOK OUTPUT - NOT FETCHED CONTENT]\n"
        "Source: correction-catcher.py (UserPromptSubmit, the repo owner's hook).\n"
        f"Possible correction from {PRINCIPAL} (matched '{m.group(0)}'). If they are correcting you, park the\n"
        "CORRECTION itself before continuing: the wrong assumption, the evidence, the fix\n"
        f"({PARK_HOW}). Not a correction? Ignore this."
    )
except Exception:
    pass
sys.exit(0)
