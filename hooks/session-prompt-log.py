#!/usr/bin/env python3
"""SessionStart hook: log the size and sections of what a session starts with.

Writes ONE JSON line to $KIT_LOG_DIR/session-start-prompt.jsonl and prints NOTHING (adds zero
context). FAILS OPEN.

HONEST LIMIT: the hook payload does not carry the assembled system prompt, so this logs the
MEASURABLE INPUTS it is built from (CLAUDE.md, the shared contract, the auto-memory index,
per-section sizes) plus, for resume/compact starts, the transcript size. The real first-turn
context size comes from tiering-score.py (usage block of the first assistant message).

Config (env, all optional):
  KIT_LOG_DIR        default ~/.claude/logs
  KIT_KB_ROOT        default ~/kb
  KIT_CONTRACT_FILE  shared contract imported by CLAUDE.md (default ~/.claude/contract.md)
  KIT_KB_FILES       comma list of hot KB files to size (default TODO.md,STATUS.md)
"""
import json
import os
import re
import sys
import time

LOG_DIR = os.path.expanduser(os.environ.get("KIT_LOG_DIR") or "~/.claude/logs")
LOG = os.path.join(LOG_DIR, "session-start-prompt.jsonl")
KB = os.path.expanduser(os.environ.get("KIT_KB_ROOT") or "~/kb")
CONTRACT = os.path.expanduser(os.environ.get("KIT_CONTRACT_FILE") or "~/.claude/contract.md")
HOT = [x.strip() for x in (os.environ.get("KIT_KB_FILES") or "TODO.md,STATUS.md").split(",") if x.strip()]


def size(p):
    try:
        return os.path.getsize(os.path.expanduser(p))
    except Exception:
        return None


def sections(p, top=8):
    try:
        text = open(os.path.expanduser(p), encoding="utf-8", errors="replace").read()
    except Exception:
        return []
    parts = re.split(r"(?m)^(?=#{1,3} )", text)
    rows = [(len(x.encode()), x.split("\n", 1)[0][:60]) for x in parts if x.strip()]
    rows.sort(reverse=True)
    return [{"bytes": b, "head": h} for b, h in rows[:top]]


try:
    payload = json.load(sys.stdin)
    cwd = payload.get("cwd") or os.getcwd()
    claude_md = os.path.join(cwd, "CLAUDE.md")
    try:
        mem = "~/.claude/projects/%s/memory/MEMORY.md" % cwd.replace(os.sep, "-")
    except Exception:
        mem = "~/.claude/projects/unknown/memory/MEMORY.md"
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "session": payload.get("session_id"),
        "source": payload.get("source"),
        "model": payload.get("model"),
        "cwd": cwd,
        "claude_md_bytes": size(claude_md),
        "shared_contract_bytes": size(CONTRACT),
        "memory_index_bytes": size(mem),
        "approx_tokens": sum(x or 0 for x in (size(claude_md), size(CONTRACT), size(mem))) // 4,
        "top_sections": sections(claude_md),
        "transcript_bytes": size(payload["transcript_path"]) if payload.get("transcript_path") else None,
        "kb_file_bytes": {n: size(os.path.join(KB, n)) for n in HOT},
    }
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(json.dumps(rec) + "\n")
except Exception:
    pass
sys.exit(0)
