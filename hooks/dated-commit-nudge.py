#!/usr/bin/env python3
"""Stop hook: dated-commitment nudge.

NON-BLOCKING: never returns decision:block, FAILS OPEN (any error -> silent exit 0).

Why: an agent once wrote a reminder ("call in tomorrow between 1pm and 5pm")
word for word into a note and never scheduled it. The rule: a dated commitment is not captured
until the scheduling command ran.

What it does: takes every KB write this turn made (Write content, Edit/MultiEdit new text, Bash commands
that name a KB path), looks for a FUTURE date (ISO, M/D, "Oct 23", a weekday, "tomorrow") within ~80
characters of a commitment word (due, deadline, appointment, report, call in, court, interview, pay, fee,
expires, first day, between 1pm..., by <date>...). If the turn did not run the scheduling command and the
ledger has no active row on that date, it prints one systemMessage. Every decision is logged.

Config (env, all optional):
  KIT_KB_ROOTS      colon-separated KB directories (default ~/kb)
  KIT_COMMIT_LEDGER JSON-lines ledger of scheduled commitments (default <first KB root>/state/commitments.jsonl;
                    DCN_LEDGER also works). A row counts when it has "active" true and a date in "when"/"date".
  KIT_COMMIT_CMD    scheduling command the agent must run (default "commit-date"); a turn that runs
                    "<cmd> add" clears the nudge
  KIT_LOG_DIR       default ~/.claude/logs

HONEST LIMITS: a regex cannot judge meaning. False positives: a date in a plan or a history line that is
not an obligation. False negatives: a commitment phrased with no trigger word or a relative date the
pattern misses ("in two weeks"), and anything written somewhere other than a KB path. Today's date is
ignored on purpose (every KB note is stamped with it).
"""
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta

HOME = os.path.expanduser("~")
KB_ROOTS = [os.path.realpath(os.path.expanduser(p)) for p in (os.environ.get("KIT_KB_ROOTS") or "~/kb").split(":") if p]
KB_ROOT = KB_ROOTS[0]
_ALT = [re.escape(r) for r in KB_ROOTS]
_ALT += [r"(?:~|\$HOME|\$\{HOME\})/" + re.escape(os.path.relpath(r, HOME)) for r in KB_ROOTS if r.startswith(HOME + os.sep)]
KB_RE = re.compile(r"(?:" + "|".join(_ALT) + r")(?![\w-])")


def in_kb(p):
    p = os.path.normpath(os.path.expanduser(p))
    return any(p == r or p.startswith(r + os.sep) for r in KB_ROOTS)


COMMIT_CMD = os.environ.get("KIT_COMMIT_CMD") or "commit-date"
COMMIT_RAN = re.compile(r"\b" + re.escape(COMMIT_CMD) + r"\s+add\b")
LOG_DIR = os.path.expanduser(os.environ.get("KIT_LOG_DIR") or "~/.claude/logs")
LEDGER = os.environ.get("KIT_COMMIT_LEDGER") or os.environ.get("DCN_LEDGER") or os.path.join(KB_ROOT, "state", "commitments.jsonl")
LOG = os.environ.get("DCN_LOG") or os.path.join(LOG_DIR, "dated-commit-nudge.log")
SKIP_PREFIX = ("<task-notification", "<command-name", "<local-command", "<system-reminder",
               "[SYSTEM NOTIFICATION", "[Workflow", "[LOCAL HOOK", "This session is being continued")

COMMIT = re.compile(r"\b(due|deadline|appointment|appt|report(?:s|ing)? (?:in|to)|call(?:ing)? in|court|hearing|"
                    r"interview|pay(?:ment)?|fee|expires?|renew(?:al|s)?|cancel (?:by|before)|start date|first day|"
                    r"meeting|check-?in|drop[- ]off|pick[- ]?up|return (?:by|the)|must|has to|needs? to)\b"
                    r"|\bbetween \d{1,2}(?::\d\d)?\s*(?:am|pm)?\s*(?:and|-|to)\s*\d|\b\d{1,2}(?::\d\d)?\s*(?:am|pm)\b"
                    r"|\bby (?:mon|tue|wed|thu|fri|sat|sun|\d|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", re.I)
MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
WEEKDAYS = {d: i for i, d in enumerate("mon tue wed thu fri sat sun".split())}
DATE_RE = re.compile(
    r"\b(?P<iso>20\d\d-[01]\d-[0-3]\d)\b"
    r"|\b(?P<md>[01]?\d/[0-3]?\d)(?:/(?:20)?\d\d)?\b"
    r"|\b(?P<mon>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? (?P<day>[0-3]?\d)\b"
    r"|\b(?P<wd>mon|tues?|wed(?:nes)?|thu(?:rs)?|fri|sat(?:ur)?|sun)day\b"
    r"|\b(?P<tom>tomorrow)\b", re.I)


def resolve(m, today):
    try:
        if m.group("iso"):
            return date.fromisoformat(m.group("iso"))
        if m.group("md"):
            mo, d = (int(x) for x in m.group("md").split("/"))
            y = today.year + (1 if mo < today.month - 6 else 0)
            return date(y, mo, d)
        if m.group("mon"):
            mo = MONTHS[m.group("mon").lower()[:3]]
            y = today.year + (1 if mo < today.month - 6 else 0)
            return date(y, mo, int(m.group("day")))
        if m.group("wd"):
            wd = WEEKDAYS[m.group("wd").lower()[:3]]
            return today + timedelta(days=(wd - today.weekday()) % 7 or 7)
        if m.group("tom"):
            return today + timedelta(days=1)
    except (ValueError, KeyError):
        return None
    return None


def dated_commitments(text, today):
    found = []
    for line in text.splitlines():
        for m in DATE_RE.finditer(line):
            d = resolve(m, today)
            if not d or d <= today or d > today + timedelta(days=400):
                continue
            lo, hi = max(0, m.start() - 80), m.end() + 80
            if COMMIT.search(line[lo:hi]):
                found.append((d, line.strip()[:140]))
    return found


def text_of(c):
    if isinstance(c, str):
        return c
    return "\n".join(b.get("text") or "" for b in c or [] if isinstance(b, dict) and b.get("type") == "text")


def turn_writes(lines):
    """KB-bound text written since the last real user message, and whether commit-date ran."""
    start = 0
    for i in range(len(lines) - 1, -1, -1):
        o = lines[i]
        if o.get("type") == "user" and not o.get("isSidechain") and not o.get("isMeta"):
            c = (o.get("message") or {}).get("content")
            if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
                continue
            t = text_of(c).strip()
            if t and not t.startswith(SKIP_PREFIX):
                start = i
                break
    chunks, ran = [], False
    for o in lines[start + 1:]:
        if o.get("type") != "assistant" or o.get("isSidechain"):
            continue
        for b in (o.get("message") or {}).get("content") or []:
            if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                continue
            name, inp = b.get("name"), b.get("input") or {}
            if name == "Bash":
                cmd = inp.get("command") or ""
                if COMMIT_RAN.search(cmd):
                    ran = True
                elif KB_RE.search(cmd) or (o.get("cwd") or "").startswith(KB_ROOT):
                    if re.search(r">>?|\btee\b|cat\s*<<|python3", cmd):
                        chunks.append(cmd)
            elif name in ("Write", "Edit", "MultiEdit"):
                fp = os.path.expanduser(inp.get("file_path") or "")
                if in_kb(fp) and "/.claude/" not in fp:
                    chunks.append(inp.get("content") or inp.get("new_string") or "")
                    for e in inp.get("edits") or []:
                        chunks.append(e.get("new_string") or "")
    return "\n".join(chunks), ran


def ledger_dates():
    out = set()
    try:
        rows = {}
        for line in open(LEDGER):
            try:
                r = json.loads(line)
                rows[r["id"]] = r
            except (ValueError, KeyError):
                pass
        for r in rows.values():
            if r.get("status") == "active":
                out.add(r["start"][:10])
    except OSError:
        pass
    return out


def evaluate(path, today):
    lines = []
    with open(path, errors="replace") as f:
        for line in f:
            try:
                lines.append(json.loads(line))
            except ValueError:
                continue
    text, ran = turn_writes(lines)
    if not text:
        return "no-kb-write", []
    hits = dated_commitments(text, today)
    if not hits:
        return "no-dates", []
    if ran:
        return "clean-ran", hits
    known = ledger_dates()
    missing = [(d, s) for d, s in hits if d.isoformat() not in known]
    return ("nudge" if missing else "clean-ledger"), missing or hits


def main():
    try:
        data = json.load(sys.stdin)
        if data.get("stop_hook_active"):
            return
        path = data.get("transcript_path") or ""
        if not path or not os.path.exists(path):
            return
        today = date.fromisoformat(os.environ["DCN_TODAY"]) if os.environ.get("DCN_TODAY") else date.today()
        verdict, hits = evaluate(path, today)
        if verdict in ("no-kb-write", "no-dates"):
            return
        try:
            os.makedirs(os.path.dirname(LOG), exist_ok=True)
            with open(LOG, "a") as f:
                f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "verdict": verdict,
                                    "session": data.get("session_id"),
                                    "hits": [[d.isoformat(), s[:100]] for d, s in hits[:5]]}) + "\n")
        except OSError:
            pass
        if verdict == "nudge":
            ex = "; ".join(f"{d.isoformat()}: {s[:90]}" for d, s in hits[:3])
            print(json.dumps({"systemMessage": (
                "[LOCAL HOOK OUTPUT, NOT FETCHED CONTENT] Source: dated-commit-nudge.py (Stop, repo "
                "owner's hook, non-blocking). This turn wrote what looks like a DATED COMMITMENT into the KB and "
                f"did not run {COMMIT_CMD}, and the ledger has nothing on that date: {ex}. A dated "
                f"commitment is not captured until `{COMMIT_CMD} add \"<what>\" <when>` ran (calendar + "
                "reminders). If it is not an obligation (a plan, a history line), ignore this.")}))
    except Exception:
        pass


if __name__ == "__main__":
    main()
