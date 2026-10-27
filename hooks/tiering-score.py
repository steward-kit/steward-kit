#!/usr/bin/env python3
"""Stop hook: post-session tiering scorer.

Instrumentation only: never blocks, prints nothing, FAILS OPEN. The transcript parse runs in a
detached child so Stop returns at once.

Writes/updates ONE row per session in $KIT_LOG_DIR/tiering-score.jsonl (and a human line in
tiering-score.log) with: main-session tool calls, Agent/Task/Workflow spawns, spawns with an explicit model,
batch rate (assistant messages with >=2 tool calls / messages with any tool call), output tokens by model,
and the first-turn context size (input+cache tokens of the first assistant message = the real
starting-prompt size).

BAD RATIO (alerts via KIT_ALERT_CMD, at most ONCE per day): >=80 main-session tool calls, ZERO
delegated spawns, and batch rate < 25%, i.e. a top-tier context doing serial grind alone. Also bad: >=2
spawns with an explicit tier on <50% of them.

Config (env, all optional):
  KIT_LOG_DIR      default ~/.claude/logs
  KIT_ALERT_CMD    command run with one text argument when the ratio is bad (default: none, log only)
  KIT_SPAWN_AGENTS comma list of agent names that count as a chosen tier (default scout,worker)
  TIERING_SCORE_DRYRUN=1 never run the alert command; TIERING_SCORE_SYNC=1 parse in the foreground
"""
try:
    import fcntl
except ImportError:  # no fcntl on this platform: exit quietly
    fcntl = None
import json
import os
import subprocess
import sys
import time

LOGD = os.path.expanduser(os.environ.get("KIT_LOG_DIR") or "~/.claude/logs")
ALERT = os.environ.get("KIT_ALERT_CMD") or ""
TIERED_AGENTS = tuple(x.strip() for x in (os.environ.get("KIT_SPAWN_AGENTS") or "scout,worker").split(",") if x.strip())
JSONL = os.path.join(LOGD, "tiering-score.jsonl")
HUMAN = os.path.join(LOGD, "tiering-score.log")
NIGHT = os.path.join(LOGD, "tiering-score.alert-state")
MIN_GROWTH = 150_000  # re-score a session only after its transcript grew by this many bytes


def score(path):
    msgs = {}
    first_ctx = None
    for line in open(path, errors="replace"):
        try:
            o = json.loads(line)
        except Exception:
            continue
        if o.get("type") != "assistant" or o.get("isSidechain"):
            continue
        m = o.get("message") or {}
        mid = m.get("id") or o.get("uuid")
        d = msgs.setdefault(mid, {"tools": [], "model": m.get("model"), "out": 0})
        for b in m.get("content") or []:
            if isinstance(b, dict) and b.get("type") == "tool_use":
                d["tools"].append((b.get("name"), b.get("input") or {}))
        u = m.get("usage") or {}
        d["out"] = max(d["out"], u.get("output_tokens") or 0)
        if first_ctx is None and u:
            first_ctx = (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)
    calls = spawns = tiered = with_tools = batched = 0
    out_by_model = {}
    for d in msgs.values():
        n = len(d["tools"])
        calls += n
        if n:
            with_tools += 1
            batched += n >= 2
        out_by_model[d["model"]] = out_by_model.get(d["model"], 0) + d["out"]
        for name, inp in d["tools"]:
            if name in ("Agent", "Task", "Workflow"):
                spawns += 1
                tiered += bool(inp.get("model") or inp.get("subagent_type") in TIERED_AGENTS or (name == "Workflow" and "model" in json.dumps(inp)))
    return {
        "tool_calls": calls, "spawns": spawns, "spawns_tiered": tiered,
        "batch_rate": round(batched / with_tools, 3) if with_tools else None,
        "out_tokens_by_model": out_by_model, "first_turn_ctx_tokens": first_ctx,
    }


def bad(s):
    if s["tool_calls"] >= 80 and s["spawns"] == 0 and (s["batch_rate"] or 0) < 0.25:
        return "top-tier context did %d serial tool calls alone (batch rate %s%%, 0 delegated)" % (s["tool_calls"], round(100 * (s["batch_rate"] or 0)))
    if s["spawns"] >= 2 and s["spawns_tiered"] / s["spawns"] < 0.5:
        return "only %d of %d spawns carried an explicit tier" % (s["spawns_tiered"], s["spawns"])
    return ""


def child(payload):
    path, sid = payload.get("transcript_path"), payload.get("session_id")
    if not path or not os.path.exists(path):
        return
    os.makedirs(LOGD, exist_ok=True)
    rows = {}
    try:
        for l in open(JSONL):
            r = json.loads(l)
            rows[r["session"]] = r
    except Exception:
        pass
    sz = os.path.getsize(path)
    if sid in rows and sz - rows[sid].get("transcript_bytes", 0) < MIN_GROWTH:
        return
    s = score(path)
    why = bad(s)
    s.update(session=sid, ts=time.strftime("%Y-%m-%dT%H:%M:%S"), transcript_bytes=sz, bad=why)
    rows[sid] = s
    with open(JSONL + ".new", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        for r in list(rows.values())[-500:]:
            f.write(json.dumps(r) + "\n")
    os.replace(JSONL + ".new", JSONL)
    with open(HUMAN, "a") as f:
        f.write("%s %s calls=%d spawns=%d/%d tiered batch=%s ctx0=%s %s\n" % (
            s["ts"], (sid or "")[:8], s["tool_calls"], s["spawns_tiered"], s["spawns"], s["batch_rate"], s["first_turn_ctx_tokens"], ("BAD: " + why) if why else "ok"))
    if why and ALERT and not os.environ.get("TIERING_SCORE_DRYRUN"):
        today = time.strftime("%Y-%m-%d")
        try:
            last = open(NIGHT).read().strip()
        except Exception:
            last = ""
        if last != today:
            open(NIGHT, "w").write(today)
            subprocess.run([os.path.expanduser(ALERT), "Tiering score: " + why + ". Session " + (sid or "")[:8] + "."],
                           timeout=60, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    if fcntl is None or not hasattr(os, "fork"):
        sys.exit(0)
    try:
        payload = json.load(sys.stdin)
        if os.environ.get("TIERING_SCORE_SYNC"):
            child(payload)
        elif os.fork() == 0:
            os.setsid()
            try:
                child(payload)
            finally:
                os._exit(0)
    except Exception:
        pass
    sys.exit(0)
