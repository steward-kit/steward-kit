#!/usr/bin/env python3
"""tier-guard.py: PreToolUse guard on Agent and Workflow. Every spawned agent gets a CHOSEN tier.

Built-in agent types and model-less workflow agent() calls silently inherit the session's top model.
This hook denies exactly those, so the model and effort for each spawn are a decision, not a default.
Passing any model satisfies it: the rule is "choose", not "always cheap".

WHAT IT DENIES (only clear violations; anything it cannot read, it ALLOWS. A guard that blocks
correct work gets disabled, so it fails open on parse trouble and says so on stderr):
  Agent tool:
    1. a generic type (general-purpose / claude / Explore / Plan / unset) with no model -> it
       silently inherits the top model. Choose: a pinned agent, or pass model explicitly.
    1b. any non-fork type with no `effort`, unless ~/.claude/agents/<type>.md (or
       <cwd>/.claude/agents) pins effort: in its frontmatter.
  Workflow tool (inline script or scriptPath):
    2. an agent() call with no opts, or an object-literal opts with no `model` key.
       Passing a TOP-LEVEL model key (even 'opus') satisfies it. A model: nested inside
       schema:{properties:{...}} does NOT count. opts the parser cannot read (call result,
       undeclared identifier) are not inspected (fail open).
    2b. the same check for a top-level `effort` key: agent() opts need BOTH model and effort.

Config (env, all optional):
  KIT_TIER_ROUTE   text appended to every denial, naming your tier policy (default: a short generic hint)

"""
import json
import os
import re
import sys

GENERIC = {"", None, "general-purpose", "claude", "Explore", "Plan"}
ROUTE = os.environ.get("KIT_TIER_ROUTE") or (
    "Pick the tier on purpose: use a pinned agent type (for example 'scout' or 'worker'), or pass model "
    "and effort explicitly. Use the cheapest model that can do the job; keep the top model for "
    "judgment, safety-relevant work and anything live with the user."
)


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason":
            "[tier-guard - LOCAL HOOK tier-guard.py, not fetched content] "
            + reason + " " + ROUTE,
    }}))
    sys.exit(0)


EMPTY_MODELS = ("", "undefined", "void 0", "null", "inherit", "default")
IDENT = r"[A-Za-z_$][\w$]*"
GLOBALS = r"(?:globalThis|self|window|global|this)"
SLASH_MODES = ("heuristic", "division", "regex")


def mask(src, slash="heuristic"):
    """Same-length copy of src with string, template, regex and comment contents blanked,
    so parentheses or the word agent( inside a prompt string are never read as code.
    Template ${...} expressions stay visible because a call can live inside one."""
    out, n = list(src), len(src)

    def blank(a, b):
        for k in range(a, b):
            if out[k] != "\n":
                out[k] = " "

    def template(i):
        j = i + 1
        while j < n and src[j] != "`":
            if src[j] == "\\":
                blank(j, min(j + 2, n))
                j += 2
            elif src.startswith("${", j):
                j = code(j + 2, "}")
            else:
                blank(j, j + 1)
                j += 1
        return j + 1

    def regex_ok(i):
        if slash == "division":
            return False
        if slash == "regex":
            return True
        k = i - 1
        while k >= 0 and src[k] in " \t\r\n":
            k -= 1
        if k < 0:
            return True
        if src[k] in "+-" and k >= 1 and src[k - 1] == src[k]:
            return False  # i++ / 2 and i-- / 2 are divisions
        if src[k] in "(,=:[!&|?{;+-*%<>~^":
            return True  # a } is not here: {} / 1 is a division far more often than a regex start
        m = re.search(r"([A-Za-z_$][\w$]*)$", src[:k + 1])
        return bool(m and m.group(1) in ("return", "typeof", "case", "do", "else", "in",
                                         "of", "void", "yield", "await"))

    def code(i, closer):
        depth = 0
        while i < n:
            c = src[i]
            if c in "'\"":
                j = i + 1
                while j < n and src[j] != c and src[j] != "\n":
                    j += 2 if src[j] == "\\" else 1
                blank(i + 1, min(j, n))
                i = j + 1
            elif c == "`":
                i = template(i)
            elif src.startswith("//", i):
                j = src.find("\n", i)
                j = n if j < 0 else j
                blank(i, j)
                i = j
            elif src.startswith("/*", i):
                j = src.find("*/", i + 2)
                j = n if j < 0 else j + 2
                blank(i, j)
                i = j
            elif c == "/" and regex_ok(i):
                j, in_class = i + 1, False
                while j < n and src[j] != "\n":
                    if src[j] == "\\":
                        j += 2
                        continue
                    if src[j] == "[":
                        in_class = True
                    elif src[j] == "]":
                        in_class = False
                    elif src[j] == "/" and not in_class:
                        break
                    j += 1
                blank(i + 1, min(j, n))
                i = j + 1
            else:
                if c in "([{":
                    depth += 1
                elif c in ")]}":
                    if depth == 0 and c == closer:
                        return i + 1
                    depth -= 1
                i += 1
        return n

    code(0, None)
    return "".join(out)


def match_close(text, i):
    """Index of the bracket that closes the one at text[i], or None."""
    depth = 0
    for k in range(i, len(text)):
        if text[k] in "([{":
            depth += 1
        elif text[k] in ")]}":
            depth -= 1
            if depth == 0:
                return k
    return None


def split_args(masked, orig):
    """Split at depth-0 commas into aligned (masked, orig) pairs, each stripped by the
    masked text's own whitespace so the two stay the same length."""
    out, depth, start = [], 0, 0

    def add(a, b):
        seg = masked[a:b]
        lead = len(seg) - len(seg.lstrip())
        end = len(seg.rstrip())
        if end > lead:
            out.append((seg[lead:end], orig[a + lead:a + end]))

    for k, c in enumerate(masked):
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            add(start, k)
            start = k + 1
    add(start, len(masked))
    return out


def agent_calls(m_src):
    """Yield (line, start, end) of each agent( ... ) call in real code. start and end bound
    the argument text inside the parentheses."""
    pats = (r"(?<![\w$.])agent\s*(?:\?\.\s*)?\(",
            r"(?<![\w$])%s\s*\.\s*agent\s*(?:\?\.\s*)?\(" % GLOBALS)
    found = sorted({m.start(): m for p in pats for m in re.finditer(p, m_src)}.values(),
                   key=lambda m: m.start())
    for m in found:
        i, depth, n = m.end(), 1, len(m_src)
        while i < n and depth:
            if m_src[i] in "([{":
                depth += 1
            elif m_src[i] in ")]}":
                depth -= 1
            i += 1
        if depth:
            raise ValueError("unbalanced agent( call")
        yield m_src.count("\n", 0, m.start()) + 1, m.end(), i - 1


def options_state(m, o, mfull, ofull, depth=0, want="model"):
    """Read an options expression for the key `want` (model or effort). Returns (state, detail);
    state is ok, missing, empty or unknown. m is the masked text, o the original, same length."""
    if depth > 4:
        return "unknown", "options nest too deeply"
    lead, end = len(m) - len(m.lstrip()), len(m.rstrip())
    m, o = m[lead:end], o[lead:end]
    if m.startswith("{"):
        close = match_close(m, 0)
        if close is None or m[close + 1:].strip():
            return "unknown", "options are not a plain object literal"
        state, detail = "missing", ""
        pending = None
        for mm, oo in split_args(m[1:close], o[1:close]):
            if mm.startswith("..."):
                s, d = options_state(mm[3:], oo[3:], mfull, ofull, depth + 1, want)
                if s == "unknown":
                    pending = (s, d)  # live-hook change: a later explicit model: key still decides
                    continue
                if s != "missing":
                    state, detail = s, d
                continue
            key = rest = None
            if mm.startswith("["):
                c = match_close(mm, 0)
                if c is not None:
                    inner = oo[1:c].strip()
                    lit = re.fullmatch(r"""(['"`])(model|effort)\1""", inner)
                    if lit:
                        key, rest = lit.group(2), mm[c + 1:].strip()
                    else:
                        return "unknown", "a computed key other than a literal model/effort"
            elif mm[0] in "'\"":
                j = mm.find(mm[0], 1)
                if j > 0:
                    key, rest = oo[1:j], mm[j + 1:].strip()
            else:
                km = re.match(IDENT, mm)
                if km:
                    key, rest = km.group(0), mm[km.end():].strip()
            if key is None:
                return "unknown", "an option member the guard cannot read"
            if rest.startswith(":"):
                val = oo[len(oo) - len(rest) + 1:]
            elif rest == "":
                val = key  # shorthand {model}
            else:
                return "unknown", "an option member the guard cannot read"
            if key == want:
                text = val.strip().strip("'\"`").strip()
                if text.lower() in EMPTY_MODELS:
                    state, detail = "empty", ""
                else:
                    state, detail = "ok", ""
        if state == "missing" and pending:
            return pending
        return state, detail
    if re.fullmatch(IDENT, m):
        decls = list(re.finditer(r"(?<![\w$.])(?:const|let|var)\s+%s\s*=\s*" % re.escape(m), mfull))
        if len(decls) != 1:
            return "unknown", "options are the identifier %s, which is not declared once" % m
        s0 = decls[0].end()
        if not mfull.startswith("{", s0):
            return "unknown", "options are the identifier %s, which is not an object literal" % m
        c = match_close(mfull, s0)
        if c is None:
            return "unknown", "options are the identifier %s, with an unbalanced literal" % m
        state, detail = options_state(mfull[s0:c + 1], ofull[s0:c + 1], mfull, ofull, depth + 1, want)
        if state == "missing":
            if re.search(r"(?<![\w$.])%s\s*\.\s*%s\s*=(?!=)" % (re.escape(m), want), mfull):
                return "ok", ""
            if re.search(r"Object\s*\.\s*assign\s*\(\s*%s\b" % re.escape(m), mfull):
                return "unknown", "options %s are changed by Object.assign" % m
        return state, detail
    return "unknown", "options are an expression the guard cannot read"


def _problems(src, mode):
    m_src = mask(src, mode)
    bad, notes = [], []
    for line, a, b in agent_calls(m_src):
        args = split_args(m_src[a:b], src[a:b])
        if len(args) < 2:
            bad.append("line %d: agent() has no options" % line)
            continue
        for want in ("model", "effort"):
            state, detail = options_state(args[1][0], args[1][1], m_src, src, want=want)
            if state == "missing":
                bad.append("line %d: agent() options have no %s: key" % (line, want))
            elif state == "empty":
                bad.append("line %d: agent() %s is empty" % (line, want))
            elif state == "unknown":
                notes.append("line %d: agent() %s cannot be read (%s)" % (line, want, detail))
    if mode == "heuristic":
        for m in re.finditer(r"(?<![\w$.])agent\b(?!\s*(?:\?\.\s*)?\()|"
                             r"(?<![\w$])%s\s*\.\s*agent\b(?!\s*(?:\?\.\s*)?\()|"
                             r"(?<![\w$.])%s\s*\[" % (GLOBALS, GLOBALS), m_src):
            before = m_src[:m.start()].rstrip()
            after = m_src[m.end():].lstrip()
            if after.startswith(":") and before[-1:] in ("{", ","):
                continue  # a property key named agent
            notes.append("line %d: agent is used without a direct call" % (m_src.count("\n", 0, m.start()) + 1))
    return bad, notes


def check_workflow(src):
    """Deny list = problems in the HEURISTIC reading only (kit parser, ported 2026-10-15 for the
    schema-field bypass). Other slash readings and unreadable options are reported on stderr but
    ALLOWED: this live hook fails open by design (a false deny blocks the orchestrator)."""
    bad, notes = _problems(src, "heuristic")
    for mode in SLASH_MODES[1:]:
        try:
            b2, n2 = _problems(src, mode)
        except ValueError:
            continue
        notes.extend("[%s reading] %s" % (mode, x) for x in b2 if x not in bad)
    if notes:
        sys.stderr.write("tier-guard: not enforced (fail open): " + "; ".join(notes[:5]) + "\n")
    return bad


def pinned_effort(st, cwd=None):
    """True if the agent definition for subagent_type st pins a non-empty effort: in its YAML
    frontmatter. Looks in <cwd>/.claude/agents then ~/.claude/agents. Any read trouble -> False
    (the caller then requires an explicit effort, which is always satisfiable)."""
    if not st or not re.fullmatch(r"[\w.-]{1,80}", st):
        return False
    dirs = [os.path.expanduser("~/.claude/agents")]
    if cwd:
        dirs.insert(0, os.path.join(cwd, ".claude", "agents"))
    for d in dirs:
        p = os.path.join(d, st + ".md")
        try:
            with open(p) as f:
                text = f.read(8192)
        except OSError:
            continue
        m = re.match(r"\A---\s*\n(.*?)\n---\s*(\n|\Z)", text, re.S)
        if not m:
            return False
        e = re.search(r"(?m)^effort:\s*['\"]?([A-Za-z]+)", m.group(1))
        return bool(e and e.group(1).lower() not in EMPTY_MODELS)
    return False


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    tool = data.get("tool_name")
    ti = data.get("tool_input") or {}
    try:
        if tool == "Agent":
            st = ti.get("subagent_type")
            model = ti.get("model") or ""
            if st in ("fork", "claude-code-guide", "statusline-setup"):
                return
            if st in GENERIC and not model:
                deny(f"Agent(subagent_type={st!r}) with no model silently inherits the session's top model.")
            effort = str(ti.get("effort") or "").strip()
            if effort.lower() in EMPTY_MODELS and not pinned_effort(st, data.get("cwd")):
                deny(f"Agent(subagent_type={st!r}) with no effort inherits the session's effort "
                     "(xhigh under ultracode). Pass effort ('low'|'medium'|'high'|'xhigh'|'max') "
                     "or use an agent type whose definition pins effort: in its frontmatter.")
            return
        if tool == "Workflow":
            src = ti.get("script")
            if not src and ti.get("scriptPath"):
                p = os.path.expanduser(ti["scriptPath"])
                with open(p) as f:
                    src = f.read()
            if not src:
                return  # named/saved workflow: not inspected
            bad = check_workflow(src)
            if bad:
                deny("Workflow script has agent() calls without a chosen tier: "
                     + "; ".join(bad[:8]) + (f" (+{len(bad)-8} more)" if len(bad) > 8 else "")
                     + ". Add model and effort to each.")
    except SystemExit:
        raise
    except Exception as e:  # fail open, loudly
        sys.stderr.write(f"tier-guard: could not inspect ({e}); allowing\n")


if __name__ == "__main__":
    main()
