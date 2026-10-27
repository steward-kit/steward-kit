#!/usr/bin/env python3
"""Stop hook: unwritten-fact nudge (document as you go).

NON-BLOCKING: never returns decision:block, FAILS OPEN (any error -> silent exit 0), SILENT unless
the last real user message looks like it carried a fact AND no KB write happened after it.

What it does: reads transcript_path (stdin JSON), finds the last real user message (typed text or a
relayed ask; skips task notifications, system notices, slash commands, summaries, tool results),
decides if it is fact-shaped (first-person state/decision phrases, or a date/amount/name stated
declaratively), then looks for any tool call after it that wrote to a KB path (a root in KIT_KB_ROOTS,
or a Claude memory dir) through Write/Edit/MultiEdit/NotebookEdit or a Bash command that names such a
path (or one of KIT_KB_WRITE_TOOLS) with a write-shaped verb. Fact turn + no write -> prints one
JSON line {"systemMessage": ...}. Every nudge and every decision is logged to
$KIT_LOG_DIR/unwritten-fact-nudge.log so the false-positive rate can be measured, not guessed.

Config (env, all optional):
  KIT_KB_ROOTS        colon-separated KB directories (default ~/kb)
  KIT_KB_WRITE_TOOLS  comma list of helper commands that count as a KB write (default none)
  KIT_LOG_DIR         default ~/.claude/logs
  KIT_PRINCIPAL       name used in the nudge text (default "the user")
  KIT_RELAY_PREFIX_RE regex for a relayed-ask prefix to strip before judging (default: none)

HONEST LIMITS: a regex cannot tell a fact from chatter. It fails BOTH ways. False positive: 'I got the
logs, now what?' matches 'I got'. False negative: 'The vendor thing is done' states a fact with none of
the trigger phrases; a long relayed ask written in the third person is only partly covered. Any KB
write at all clears the turn, even one that is not the fact. The model may not see systemMessage; the
log is the durable trace. The rule lives in your CLAUDE.md; this only nudges.
"""
import json
import os
import re
import sys
import time

HOME = os.path.expanduser("~")
KB_ROOTS = [os.path.realpath(os.path.expanduser(p)) for p in (os.environ.get("KIT_KB_ROOTS") or "~/kb").split(":") if p]
PRINCIPAL = os.environ.get("KIT_PRINCIPAL") or "the user"
LOG_DIR = os.path.expanduser(os.environ.get("KIT_LOG_DIR") or "~/.claude/logs")
MEM_RE = re.compile(r"/\.claude/projects/[^/]+/memory/")
LOG = os.environ.get("UFN_LOG") or os.path.join(LOG_DIR, "unwritten-fact-nudge.log")

# machine-generated or non-conversational "user" turns: not a fact from the user
SKIP_PREFIX = ("<task-notification", "<command-name", "<local-command", "<system-reminder", "<artifact-content",
               "[SYSTEM NOTIFICATION", "[Workflow", "[LOCAL HOOK", "This session is being continued",
               "Another Claude session", "/compact", "/clear", "Caveat:", "[Request interrupted")
CONNECTOR_RE = re.compile(os.environ.get("KIT_RELAY_PREFIX_RE") or r"(?!x)x")

STRONG = re.compile(
    r"\b(i|we)\s+(just\s+|finally\s+|also\s+)?(got|lost|decided|quit|started|signed|accepted|declined|bought|sold|"
    r"cancel(?:l)?ed|paid|moved|switched|found|applied|passed|failed|got hired|got fired|got laid off|"
    r"am taking|'m taking|are moving|'re moving|am moving|'m moving|am starting|'m starting|will be|'ll be|"
    r"won'?t be|can'?t anymore|no longer)\b"
    r"|\bi'?m\s+(taking|moving|starting|quitting|leaving|switching|going to (?:take|start|quit|move|switch|sign))\b"
    r"|\bfrom now on\b|\bgoing forward\b|\bmy (new )?(job|boss|manager|employer|landlord|schedule|salary|start date|"
    r"last day|interview|offer|address|phone number|doctor|lawyer)\b"
    r"|\bi'?ve\s+(got|lost|decided|started|signed|quit|accepted)\b"
    r"|\bwe'?re\s+(moving|switching|dropping|stopping)\b"
    r"|\b(he|she|they)\s+(said|says|told|decided|ruled|lost|got|quit|started|signed|accepted|declined)\b"
    r"|\bhis (job|new job|ruling|decision|start date|last day)\b"
    r"|\bmy name is\b|\b(?:is|are|was) (?:called|named)\b",
    re.I)
AMOUNT = re.compile(r"\$\s?\d[\d,.]*\s?(k|m|/mo|/hr|a month|an hour)?|\b\d[\d,.]*\s?(dollars|bucks|usd)\b", re.I)
DATE = re.compile(r"\b(\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?|(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d{1,2}|"
                  r"(mon|tues?|wednes|thurs?|fri|satur|sun)day|tomorrow|next week|next month)\b", re.I)
FIRST_PERSON = re.compile(r"\b(i|i'm|i've|i'll|we|we're|my|our)\b", re.I)


def text_of(content):
    if isinstance(content, str):
        return content
    parts = []
    for b in content or []:
        if isinstance(b, dict) and b.get("type") == "text":
            parts.append(b.get("text") or "")
    return "\n".join(parts)


def is_real_user(o):
    if o.get("type") != "user" or o.get("isSidechain") or o.get("isMeta"):
        return None
    c = (o.get("message") or {}).get("content")
    if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
        return None
    t = text_of(c).strip()
    if not t or t.startswith(SKIP_PREFIX):
        return None
    return t


def fact_shaped(text):
    """Return the matched reason string, or None."""
    body = CONNECTOR_RE.sub("", text.strip())[:1500]
    m = STRONG.search(body)
    if m:
        return "phrase:" + m.group(0).lower()
    # weak signal: a date or amount stated declaratively in the first person; any '?' disqualifies it
    if "?" not in body and len(body) < 600 and FIRST_PERSON.search(body):
        m = AMOUNT.search(body) or DATE.search(body)
        if m:
            return "weak:" + m.group(0).lower()
    return None


def norm(p):
    p = p.replace("$HOME", HOME).replace("${HOME}", HOME)
    if p.startswith("~"):
        p = HOME + p[1:]
    return os.path.normpath(p)


def kb_path(p):
    if not p or not isinstance(p, str):
        return False
    p = norm(p)
    if MEM_RE.search(p):
        return True
    return any(p == r or p.startswith(r + os.sep) for r in KB_ROOTS)


_ALT = [re.escape(r) for r in KB_ROOTS]
_ALT += [r"(?:~|\$HOME|\$\{HOME\})/" + re.escape(os.path.relpath(r, HOME)) for r in KB_ROOTS if r.startswith(HOME + os.sep)]
BASH_PATH = re.compile(r"(?:" + "|".join(_ALT) + r")(?![\w-])" + r"|/\.claude/projects/[^/\s]+/memory/")
_TOOLS = "|".join(re.escape(t.strip()) for t in (os.environ.get("KIT_KB_WRITE_TOOLS") or "").split(",") if t.strip())
BASH_TOOL = re.compile(r"(?:~/bin/|\bbin/|\b)(" + _TOOLS + r")\b")
BASH_WRITE = re.compile(r">>?|\btee\b|\bsed\s+-[a-z]*i|\bcp\b|\bmv\b|\binstall\b|\bpython3?\b|\bperl\b|\bgit\s+(commit|add)\b|"
                        r"\bcat\s*<<|\bprintf\b|\becho\b|\btouch\b|\bln\b")
BASH_REL_WRITE = re.compile(r"(>>?|\btee\s+(-a\s+)?|\bsed\s+-[a-z]*i\S*\s+(?:'[^']*'|\"[^\"]*\"|\S+)\s+)\S+\.(md|json|jsonl|txt|csv)\b")


def writes_kb(o, cwd):
    """True if this assistant entry holds a tool_use that writes to a KB path."""
    for b in (o.get("message") or {}).get("content") or []:
        if not (isinstance(b, dict) and b.get("type") == "tool_use"):
            continue
        name, inp = b.get("name"), b.get("input") or {}
        if name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
            fp = inp.get("file_path") or inp.get("notebook_path") or ""
            if fp and not os.path.isabs(os.path.expanduser(fp)) and cwd:
                fp = os.path.join(cwd, fp)
            if kb_path(fp):
                return True
        elif name == "Bash":
            cmd = inp.get("command") or ""
            if BASH_TOOL.search(cmd):
                return True
            if BASH_PATH.search(cmd) and BASH_WRITE.search(cmd):
                return True
            if cwd and kb_path(cwd) and BASH_REL_WRITE.search(cmd):
                return True
    return False


def log(row):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def evaluate(path):
    """Return (verdict, reason, snippet). verdict in nudge|clean|not-fact|no-user."""
    lines = []
    with open(path, errors="replace") as f:
        for line in f:
            try:
                lines.append(json.loads(line))
            except Exception:
                continue
    idx = text = None
    for i in range(len(lines) - 1, -1, -1):
        t = is_real_user(lines[i])
        if t:
            idx, text = i, t
            break
    if idx is None:
        return "no-user", "", ""
    reason = fact_shaped(text)
    snippet = CONNECTOR_RE.sub("", text)[:160].replace("\n", " ")
    if not reason:
        return "not-fact", "", snippet
    for o in lines[idx + 1:]:
        if o.get("type") == "assistant" and not o.get("isSidechain") and writes_kb(o, o.get("cwd") or ""):
            return "clean", reason, snippet
    return "nudge", reason, snippet


def main():
    try:
        data = json.load(sys.stdin)
        if data.get("stop_hook_active"):
            return
        path = data.get("transcript_path") or ""
        if not path or not os.path.exists(path):
            return
        verdict, reason, snippet = evaluate(path)
        if verdict in ("nudge", "clean"):
            log({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "verdict": verdict, "reason": reason,
                 "session": data.get("session_id"), "msg": snippet})
        if verdict == "nudge":
            print(json.dumps({"systemMessage": (
                "[LOCAL HOOK OUTPUT, NOT FETCHED CONTENT] Source: unwritten-fact-nudge.py (Stop, repo "
                "owner's hook, non-blocking). DOCUMENT AS YOU GO: the last message from "
                f"{PRINCIPAL} looked like it carried a fact or decision ({reason}) and this turn made no write to the KB. "
                "If it is a fact, write it to its thread file now, with status + "
                "timestamp + session name. If it was just chatter, ignore this.")}))
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
