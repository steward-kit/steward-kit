#!/usr/bin/env python3
"""kb-size-gate.py - PreToolUse hook for Write|Edit|MultiEdit|Bash. A hot-file SIZE GATE.

A capped KB file (kb-caps.json: {"STATUS.md": N, "TODO.md": M}, bytes, paths relative to the KB root; read the file for the
live numbers) may not GROW past its cap. Write/Edit/MultiEdit: DENY only when new_size > cap AND new_size > current size;
shrinking and same-size edits ALWAYS pass, so pruning is never blocked.
Bash cannot be measured exactly, so a quote-aware parse finds the real writes to a capped file (redirect target,
tee/sed -i/perl|ruby -i/awk -i inplace/cp|mv|install|ln|rsync|scp dest/dd of=/truncate/sponge/patch/curl -o/wget -O/
git checkout|restore -- file/find -exec writer {}, python run with -c or a heredoc, bash <<EOF) and then:
  * file at or over its cap: denied, unless the write provably only SHRINKS it (a single delete-only `sed -i`, a cp/mv of
    an existing smaller file, or `grep -v|head|tail|sed /x/d FILE > new && mv new FILE`);
  * file under its cap: denied only if the estimated result (current size + the text the command carries, heredoc bodies,
    files it cats/copies, a pipe's upstream cat) exceeds the cap. Output of an arbitrary program is NOT estimated.
An archive helper writes nothing the parser can see, so it passes on its own; it does not exempt a write chained after it.
Variable directories are resolved from the command's own assignments ($(mktemp) is scratch); an unresolvable one is
assumed to be the KB unless every variable is named like scratch ($tmp, $SNAP). Python writes are looked for only in code
that is actually executed, never in grep patterns or commit messages; a script FILE that python runs is not read.
Override: a one-shot token file $KB_GATE_STATE/override-<session_id>.json holding {"reason": "...", "expires": <epoch seconds>};
the next refusal for that session consumes it (and logs). Write it with your own helper or by hand (see hooks/README.md). FAILS OPEN on any error of its own (logged). No network, no subprocess.

Config (env, all optional): KB_GATE_ROOT (else KIT_KB_ROOT, else ~/kb), KB_GATE_CAPS (default <root>/.claude/kb-caps.json),
KB_GATE_STATE (default ~/.local/state/kb-gate).
"""
import fnmatch
import json
import os
import re
import sys
import time

HOME = os.path.expanduser("~")
ME = os.path.realpath(__file__)


def root():
    return os.path.realpath(os.environ.get("KB_GATE_ROOT") or os.path.expanduser(os.environ.get("KIT_KB_ROOT") or "~/kb"))


def caps_path():
    return os.environ.get("KB_GATE_CAPS") or os.path.join(root(), ".claude", "kb-caps.json")


def state_dir():
    return os.environ.get("KB_GATE_STATE") or os.path.join(HOME, ".local", "state", "kb-gate")


def log(line):
    """Logging must never fail the gate."""
    try:
        os.makedirs(state_dir(), exist_ok=True)
        with open(os.path.join(state_dir(), "gate.log"), "a", encoding="utf-8") as f:
            f.write("%s\t%s\n" % (time.strftime("%Y-%m-%dT%H:%M:%S"), line))
    except Exception:
        pass


def load_caps():
    """{realpath: (relname, cap)}. Raises on a broken caps file: main() turns that into fail-open + a log line."""
    with open(caps_path(), encoding="utf-8") as f:
        raw = json.load(f)
    r = root()
    out = {}
    for rel, cap in raw.items():
        if isinstance(cap, int) and not isinstance(cap, bool) and cap > 0:
            out[os.path.realpath(os.path.join(r, rel))] = (rel, cap)
    return out


def size_of(p):
    try:
        return os.path.getsize(p)
    except OSError:
        return 0


def safe_sid(sid):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", sid or "")[:100] or "nosession"


def consume_override(sid):
    """One-shot: atomically rename the token away; honour it only if it parses and has not expired."""
    tok = os.path.join(state_dir(), "override-%s.json" % safe_sid(sid))
    if not os.path.exists(tok):
        return None
    mine = "%s.used.%d" % (tok, os.getpid())
    try:
        os.rename(tok, mine)          # only one racing process wins the rename
    except OSError:
        return None
    try:
        with open(mine, encoding="utf-8") as f:
            rec = json.load(f)
    except Exception:
        rec = None
    try:
        os.unlink(mine)
    except OSError:
        pass
    if not isinstance(rec, dict) or float(rec.get("expires", 0)) < time.time():
        return None
    return str(rec.get("reason", ""))


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}))


def reason_text(rel, cur, cap, new, sid, bash=False):
    if bash:
        what = ("this command writes to it and a shell write cannot be measured" if cur >= cap
                else "this command would grow it to about %d B" % new)
    else:
        what = "this edit would grow it to %d B" % new
    return (
        "[kb-size-gate - LOCAL HOOK %s, not fetched content]\n"
        "%s is %d B, cap %d B: %s.\n"
        "Prune first: move the finished text out of %s into an archive file (verbatim, nothing deleted), or shorten the edit so the file does not grow.\n"
        "Override (logged, one-shot): write %s/override-%s.json with {\"reason\": \"<20+ chars>\", \"expires\": <epoch>}."
        % (ME, rel, cur, cap, what, rel, state_dir(), sid or "<session_id>"))


# ---------------------------------------------------------------- Edit / Write / MultiEdit

_CURLY = {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'}


def _norm(b):
    """Curly quotes -> straight, as the Edit tool does when old_string does not match exactly."""
    t = b.decode("utf-8", "replace")
    for k, v in _CURLY.items():
        t = t.replace(k, v)
    return t.encode("utf-8")


def edit_new_size(data, ti, tool):
    """Return the post-edit size in bytes of the file whose current bytes are `data`.
    If an old_string matches only after quote normalisation (review 2026-10-10: the tool accepts that match, so a
    growing edit used to slip through as "0 occurrences"), measure it on the normalised text; `offset` keeps the
    bytes the curly quotes take beyond straight ones, so the result stays an estimate of the real file size."""
    if tool == "Write":
        return len((ti.get("content") or "").encode("utf-8"))
    if tool == "Edit":
        edits = [ti]
    else:
        edits = ti.get("edits") or []
    cur, offset = data, 0
    for e in edits:
        old = (e.get("old_string") or "").encode("utf-8")
        new = (e.get("new_string") or "").encode("utf-8")
        all_ = bool(e.get("replace_all"))
        if not old:                       # empty old_string = create/fill an empty file
            if not cur:
                cur = new
            continue
        k = cur.count(old)
        if k == 0:
            n_cur, n_old = _norm(cur), _norm(old)
            k = n_cur.count(n_old)
            if k == 0:                    # the tool itself will fail this edit
                continue
            offset += len(cur) - len(n_cur)
            cur, old = n_cur, n_old
        if tool == "Edit":                # size - len(old)*k + len(new)*k, k = occurrences if replace_all else 1
            kk = k if all_ else 1
            return len(cur) + offset - len(old) * kk + len(new) * kk
        cur = cur.replace(old, new) if all_ else cur.replace(old, new, 1)
    return len(cur) + offset


# ---------------------------------------------------------------- Bash
# Reviewed 2026-10-10: the first version matched verbs and `>` anywhere in the raw text, so `grep -n install TODO.md`,
# `git commit -m "x -> TODO.md"` and heredoc bodies were DENIED (over-breadth is what kills guards),
# while `sed -i '1d;2d' TODO.md` and `2>> TODO.md` slipped through. Now a small quote-aware lexer splits the command
# into simple commands; only REAL redirect targets and the file arguments of known writing verbs count, and `cd` is
# followed. Attack round 2026-10-10 (size-gate attack suite, FA1-FA4/FD1-FD5) tightened it again: python writes are
# looked for only in code that is actually EXECUTED (-c argument, heredoc body), a call to the KB archive helper exempts only itself,
# variable directories are resolved from the command's own assignments, and a write that only shrinks passes.

SCRATCH = "/tmp/.kb-gate-scratch"      # stand-in for "$(mktemp -d)": a directory that is provably not the KB
GLOBCH = re.compile(r"[*?\[]")
KBISH = re.compile(r"kb|vault|root|todo|status|repo|home|base", re.I)
SCRATCHY = re.compile(r"tmp|temp|scratch|snap|bak|backup|stag(?:e|ing)|sandbox|clone|fixture|trash|^out", re.I)

_PYSTR = re.compile(r"""[rRbBuUfF]{0,2}(["'])((?:\\.|(?!\1)[^\\\n])*)\1""")


def _py_args(code, i):
    """Text inside the parenthesis that opens just before code[i] (quote-aware), and the index of its close."""
    depth, j, q, n = 1, i, None, len(code)
    while j < n:
        c = code[j]
        if q:
            if c == "\\":
                j += 2
                continue
            if c == q:
                q = None
        elif c in "\"'":
            q = c
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                return code[i:j], j
        j += 1
    return code[i:], n


def _split_top(args):
    parts, depth, q, buf, j, n = [], 0, None, [], 0, len(args)
    while j < n:
        c = args[j]
        if q:
            buf.append(c)
            if c == "\\" and j + 1 < n:
                buf.append(args[j + 1])
                j += 2
                continue
            if c == q:
                q = None
        elif c in "\"'":
            q = c
            buf.append(c)
        elif c in "([{":
            depth += 1
            buf.append(c)
        elif c in ")]}":
            depth -= 1
            buf.append(c)
        elif c == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(c)
        j += 1
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def _sub_home(t):
    """$HOME / ${HOME} -> the home directory, but not the front of $HOMELAB."""
    return re.sub(r"\$\{HOME\}|\$HOME(?!\w)", lambda m: HOME, t)


def prefix_is_target(pre, target_dir, cwd, command):
    """Does the directory prefix written before a file name (inside a python string literal) point at the capped
    file's directory? An unresolvable prefix ($VAR, backtick) is assumed to."""
    pre = pre or ""
    if pre in ("", "./"):
        if cwd and os.path.realpath(cwd) == target_dir:
            return True
        return os.path.basename(target_dir) in command
    p = pre.rstrip("/") or "/"
    if re.search(r"\$(?!\{?HOME\b)|`", p):
        return True
    p = re.sub(r"^~(?=/|$)", HOME, p)
    p = _sub_home(p)
    if not os.path.isabs(p):
        p = os.path.join(cwd or os.getcwd(), p)
    return os.path.realpath(os.path.normpath(p)) == target_dir


def _py_dir_ok(expr, name, target_dir, cwd, command):
    """A path expression that names `name`: does it point into target_dir (or can we not tell)? Looks at every string
    literal in it, so os.path.join(expanduser('~/kb'), 'TODO.md') and '/home/x/kb/TODO.md' both count."""
    cands = []
    for m in _PYSTR.finditer(expr):
        lit = m.group(2)
        if lit == name:
            continue
        if lit.endswith("/" + name):
            cands.append(lit[:-len(name)])
        elif lit.startswith(("/", "~", "./", "../")) or "$" in lit or lit == ".":
            cands.append(lit.rstrip("/") + "/")
    if not cands:
        return prefix_is_target("", target_dir, cwd, command)
    return any(prefix_is_target(c, target_dir, cwd, command) for c in cands)


def py_writes_target(code, real, cwd, command):
    """True if python source `code` (a -c argument or a heredoc body that python RUNS) opens/copies/moves onto `real`.
    Raw-text matching of the whole command used to deny `grep "open('TODO.md','a')"` and a commit message (FD2) and to
    miss os.path.join(...) and variable paths (FA2). Now: find the write calls, take their argument expressions, and ask
    whether the expression names the file (directly or through a variable assigned from such an expression)."""
    name, tdir = os.path.basename(real), os.path.dirname(real)
    lit_rx = re.compile(r"""(["'])(?:[^"'\n]*/)?""" + re.escape(name) + r"""\1""")
    tainted = set()

    def direct(expr):
        return bool(lit_rx.search(expr)) and _py_dir_ok(expr, name, tdir, cwd, command)

    def hit(expr):
        if direct(expr):
            return True
        return any(re.search(r"(?<![\w.])%s(?![\w(])" % re.escape(v), expr) for v in tainted)

    for _ in range(3):
        for m in re.finditer(r"(?:^|[;\n])[ \t]*([A-Za-z_]\w*)[ \t]*=(?!=)[ \t]*([^\n;]+)", code):
            if m.group(1) not in tainted and not re.search(r"\bopen\s*\(|\.read", m.group(2)) and hit(m.group(2)):
                tainted.add(m.group(1))

    for m in re.finditer(r"\bopen\s*\(", code):
        pre = code[max(0, m.start() - 8):m.start()]
        if pre.endswith(".") and not re.search(r"(?:io|codecs)\.$", pre):
            continue                                              # x.open('a'): the method pass below
        args, _e = _py_args(code, m.end())
        parts = _split_top(args)
        if not parts:
            continue
        first = re.sub(r"^file\s*=\s*", "", parts[0])
        mode = None
        for p in parts[1:]:
            if p.startswith("mode"):
                mode = re.sub(r"^mode\s*=\s*", "", p)
                break
        if mode is None and len(parts) > 1 and not re.match(r"[A-Za-z_]\w*\s*=", parts[1]):
            mode = parts[1]
        if mode is None:
            continue                                              # default 'r'
        lit = _PYSTR.fullmatch(mode)
        writes = (not lit) or any(ch in lit.group(2) for ch in "awx+")
        if writes and hit(first):
            return True
    for m in re.finditer(r"\.(?:write_text|write_bytes)\s*\(|\.open\s*\(\s*(?:mode\s*=\s*)?[\"'](?:[awx]|r\+)", code):
        seg = code[:m.start()].rsplit("\n", 1)[-1].rsplit(";", 1)[-1]
        if hit(seg):
            return True
    for m in re.finditer(r"\b(?:shutil\.(?:copy\w*|move)|os\.(?:replace|rename))\s*\(", code):
        parts = _split_top(_py_args(code, m.end())[0])
        if len(parts) >= 2 and hit(parts[1]):
            return True
    for m in re.finditer(r"\bos\.open\s*\(", code):
        args = _py_args(code, m.end())[0]
        parts = _split_top(args)
        if parts and re.search(r"O_(?:WRONLY|RDWR|APPEND|CREAT|TRUNC)", args) and hit(parts[0]):
            return True
    for m in re.finditer(r"\bfileinput\.(?:input|FileInput)\s*\(", code):
        args = _py_args(code, m.end())[0]
        if re.search(r"inplace\s*=\s*(?:True|1)", args) and hit(args):
            return True
    return False


class Word(object):
    __slots__ = ("text", "var")

    def __init__(self, text, var):
        self.text, self.var = text, var       # text = quote-removed; var = contained an unquoted/dq $ or backtick


_REDIR_RX = re.compile(r"(\d*)(&>>|&>|>>|>\||>&|<<<|<<-|<<|<>|<&|>|<)")
_OPS = (";;", "&&", "||", "|&", ";", "&", "|", "(", ")")


def lex(cmd):
    """Tokens: ("W", Word) | ("OP", op) | ("R", redirect-op) | ("HD", [body]). Quotes removed, comments skipped,
    $( ) / backticks / process substitution turned into ( ) / ` operators. A heredoc body is not tokenised; it is
    attached (as one string) to the ("HD", holder) token that follows its `<<` so that code fed to python/bash can be
    inspected while heredoc text that merely MENTIONS a write stays inert."""
    toks, heredocs = [], []
    st = {"buf": [], "var": False, "in": False, "delim": None}

    def flush():
        if st["in"]:
            w = Word("".join(st["buf"]), st["var"])
            if st["delim"] is not None:
                holder = []
                heredocs.append((w.text, st["delim"], holder))
                toks.append(("HD", holder))
                st["delim"] = None
            else:
                toks.append(("W", w))
        st["buf"], st["var"], st["in"] = [], False, False

    i, n = 0, len(cmd)
    while i < n:
        c = cmd[i]
        if c in " \t\r":
            flush(); i += 1; continue
        if c == "\n":
            flush(); toks.append(("OP", "\n")); i += 1
            while heredocs:                                   # read each pending heredoc body
                delim, strip, holder = heredocs.pop(0)
                body = []
                while i < n:
                    j = cmd.find("\n", i)
                    line = cmd[i:] if j < 0 else cmd[i:j]
                    i = n if j < 0 else j + 1
                    if (line.lstrip("\t") if strip else line) == delim:
                        break
                    body.append(line)
                holder.append("\n".join(body))
            continue
        if c == "#" and not st["in"]:
            j = cmd.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == "\\":
            if cmd.startswith("\\\n", i):
                i += 2; continue
            st["buf"].append(cmd[i + 1:i + 2]); st["in"] = True; i += 2; continue
        if c == "'":
            j = cmd.find("'", i + 1)
            j = n if j < 0 else j
            st["buf"].append(cmd[i + 1:j]); st["in"] = True; i = j + 1; continue
        if c == '"':
            i += 1; st["in"] = True; depth = 0
            while i < n:
                d = cmd[i]
                if d == "\\" and i + 1 < n:
                    nx = cmd[i + 1]
                    if nx in '"\\$`':
                        st["buf"].append(nx)
                    elif nx != "\n":
                        st["buf"].append(cmd[i:i + 2])
                    i += 2; continue
                if d == '"' and depth == 0:
                    break
                if d in "$`":
                    st["var"] = True
                    if cmd.startswith("$(", i):
                        depth += 1
                elif d == ")" and depth:
                    depth -= 1
                st["buf"].append(d); i += 1
            i += 1
            continue
        if c == "$":
            if cmd.startswith("$(", i):
                flush(); toks.append(("OP", "(")); i += 2; continue
            st["var"] = True; st["in"] = True
            if cmd.startswith("${", i):
                j = cmd.find("}", i)
                j = n - 1 if j < 0 else j
                st["buf"].append(cmd[i:j + 1]); i = j + 1; continue
            st["buf"].append(c); i += 1; continue
        if c == "`":
            flush(); toks.append(("OP", "`")); i += 1; continue
        m = None
        if c in "<>" or cmd.startswith("&>", i) or (c.isdigit() and not st["in"]):
            m = _REDIR_RX.match(cmd, i)
        if m:
            flush()
            if not m.group(1) and m.group(2) in ("<", ">") and cmd.startswith("(", m.end()):
                toks.append(("OP", "(")); i = m.end() + 1; continue        # process substitution <( ) / >( )
            toks.append(("R", m.group(2)))
            if m.group(2) in ("<<", "<<-"):
                st["delim"] = m.group(2) == "<<-"
            i = m.end(); continue
        if c in ";&|()":
            flush()
            for op in _OPS:
                if cmd.startswith(op, i):
                    toks.append(("OP", op)); i += len(op); break
            continue
        st["buf"].append(c); st["in"] = True; i += 1
    flush()
    return toks


def simple_commands(toks):
    """[("cmd", words, [(redir_op, Word)], [heredoc holders], after_pipe) | ("push",) | ("pop",)] in order;
    ( $( ` open a cwd scope, ) ` close it. after_pipe: this command reads the previous one's output."""
    out, words, redirs, hds, tick, prev = [], [], [], [], False, None
    i = 0
    while i < len(toks):
        kind, v = toks[i]
        if kind == "W":
            words.append(v)
        elif kind == "HD":
            hds.append(v)
        elif kind == "R":
            if v not in ("<<", "<<-") and i + 1 < len(toks) and toks[i + 1][0] == "W":
                redirs.append((v, toks[i + 1][1])); i += 1
        else:
            if words or redirs or hds:
                out.append(("cmd", words, redirs, hds, prev in ("|", "|&")))
            words, redirs, hds = [], [], []
            if v == "(" or (v == "`" and not tick):
                out.append(("push",))
            elif v == ")" or v == "`":
                out.append(("pop",))
            if v == "`":
                tick = not tick
            prev = v
        i += 1
    if words or redirs or hds:
        out.append(("cmd", words, redirs, hds, prev in ("|", "|&")))
    return out


_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_WRAPPERS = {"sudo": {"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U"}, "env": {"-u", "-C", "-S"},
             "nice": {"-n"}, "ionice": {"-c", "-n", "-p"}, "timeout": {"-s", "-k"}, "stdbuf": set(),
             "xargs": {"-I", "-n", "-P", "-L", "-d", "-s", "-a", "-E", "-l"}, "command": set(), "builtin": set(),
             "nohup": set(), "time": set(), "exec": set(), "{": set(), "!": set(), "if": set(), "then": set(),
             "else": set(), "elif": set(), "do": set(), "while": set(), "until": set()}


def strip_wrappers(words):
    i = 0
    while i < len(words):
        t = words[i].text
        if _ASSIGN.match(t):
            i += 1; continue
        b = os.path.basename(t)
        if b not in _WRAPPERS:
            break
        argopts = _WRAPPERS[b]
        i += 1
        while i < len(words) and (words[i].text.startswith("-") or (b == "env" and _ASSIGN.match(words[i].text))):
            i += 2 if words[i].text in argopts else 1
        if b == "timeout" and i < len(words):
            i += 1                                            # the duration
    return words[i:]


def _nonopt(args):
    out, dd = [], False
    for w in args:
        if dd or not w.text.startswith("-") or w.text == "-":
            out.append(w)
        elif w.text == "--":
            dd = True
    return out


def _cluster_has(w, letter, stops):
    """Short-option cluster (-pi, -ni.bak) containing `letter` before any option that takes the rest as its value."""
    if len(w) < 2 or not w.startswith("-") or w.startswith("--"):
        return False
    for ch in w[1:]:
        if ch == letter:
            return True
        if ch in stops:
            return False
    return False


_OUT_REDIRS = (">", ">>", ">|", "&>", "&>>", "<>")
_REPLACE_REDIRS = (">", ">|", "&>", "<>", ">&")
_SIZE_RX = re.compile(r"^([+-]?)(\d+)([KMG]?)B?$", re.I)


def _trunc_size(args):
    """(bytes, absolute?) from truncate's -s/--size, or None."""
    t = [w.text for w in args]
    val = None
    for k, x in enumerate(t):
        if x in ("-s", "--size") and k + 1 < len(t):
            val = t[k + 1]
        elif x.startswith("--size="):
            val = x[7:]
        elif x.startswith("-s") and len(x) > 2 and not x.startswith("--"):
            val = x[2:]
    m = _SIZE_RX.match(val or "")
    if not m:
        return None
    mult = {"": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3}[m.group(3).upper()]
    return int(m.group(2)) * mult, m.group(1) == ""


_SED_ADDR = r"(?:\d+(?:~\d+)?|\$|/(?:[^/\\]|\\.)*/[IM]*)"
_SED_DEL = re.compile(r"^\s*(?:%s(?:\s*,\s*%s)?)?\s*!?\s*d\s*$" % (_SED_ADDR, _SED_ADDR))


def sed_delete_only(args):
    """True if the script is ONE plain `d` command (so the output can only be smaller). Anything else (-f, s///, a/i/c,
    y, r, w, several commands like '1d;2d', a `;` inside a regex) returns False, the safe direction: a multi-command script
    is not recognised as a shrink even when every part is a delete."""
    scripts, k, bare = [], 0, []
    while k < len(args):
        t = args[k].text
        if t in ("-e", "--expression") and k + 1 < len(args):
            scripts.append(args[k + 1].text); k += 2; continue
        if t.startswith("--expression="):
            scripts.append(t[13:])
        elif t in ("-f", "--file") or t.startswith("--file=") or (t.startswith("-") and not t.startswith("--")
                                                                  and "f" in t.split("i")[0]):
            return False
        elif not t.startswith("-"):
            bare.append(t)
        k += 1
    if not scripts and bare:
        scripts = [bare[0]]
    parts = [p for s in scripts for p in re.split(r"[;\n]", s)]
    parts = [p for p in parts if p.strip()]
    return len(parts) == 1 and bool(_SED_DEL.match(parts[0]))


_SED_LIT = re.compile(r"^\s*s(?P<d>[/|#,:@])(?P<a>(?:(?!(?P=d))[^\\.\[\]*^$+?(){}|&\n])+)(?P=d)(?P<b>(?:(?!(?P=d))[^\\&\n])*)(?P=d)g?\s*$")


def sed_nongrow(args):
    """Replay fix 2026-10-10: True if the in-place script can only keep the file the same size or shrink it: a delete-only
    script, or `s` commands whose pattern is a plain literal (no regex metacharacter, no backslash) and whose replacement is a
    plain literal no longer than it (no `&`, no backslash; only the `g` flag, so no `w`/`e`). Each match is replaced by a
    string no longer than itself. Anything else returns False, the safe direction."""
    if sed_delete_only(args):
        return True
    scripts, k, bare = [], 0, []
    while k < len(args):
        t = args[k].text
        if t in ("-e", "--expression") and k + 1 < len(args):
            scripts.append(args[k + 1].text); k += 2; continue
        if t.startswith("--expression="):
            scripts.append(t[13:])
        elif t in ("-f", "--file") or t.startswith("--file=") or (t.startswith("-") and not t.startswith("--")
                                                                  and "f" in t.split("i")[0]):
            return False
        elif not t.startswith("-"):
            bare.append(t)
        k += 1
    if not scripts and bare:
        scripts = [bare[0]]
    parts = [p for s in scripts for p in s.split("\n")]
    parts = [p for p in parts if p.strip()]
    if not parts:
        return False
    for p in parts:
        m = _SED_LIT.match(p)
        if not m or len(m.group("b").encode()) > len(m.group("a").encode()):
            return False
    return True


_GREP_OK_SHORT = set("vEFGiwxqsaIUz")
_GREP_OK_LONG = {"--invert-match", "--ignore-case", "--extended-regexp", "--fixed-strings", "--basic-regexp",
                 "--word-regexp", "--line-regexp", "--text", "--no-messages", "--perl-regexp", "--no-ignore-case"}


def filter_input(ws, redirs):
    """If ws is a command whose output can only be a SUBSET of its single input file (grep without -n/-b/-H/-r/context,
    head/tail, a delete-only sed), return that input file's Word; else None."""
    if not ws:
        return None
    verb, args = os.path.basename(ws[0].text), ws[1:]
    stdin = [w for op, w in redirs if op == "<"]
    if verb in ("grep", "egrep", "fgrep"):
        for w in args:
            t = w.text
            if t.startswith("--") and t != "--":
                if t not in _GREP_OK_LONG:
                    return None
            elif t.startswith("-") and len(t) > 1 and t != "--":
                if not set(t[1:]) <= _GREP_OK_SHORT:
                    return None
        na = _nonopt(args)
        if len(na) == 2 and not stdin:
            return na[1]
        if len(na) == 1 and len(stdin) == 1:
            return stdin[0]
        return None
    if verb in ("head", "tail"):
        for w in args:
            t = w.text
            if t.startswith("-") and not re.fullmatch(r"-\d+|-[nc]\d*|--lines=.*|--bytes=.*|-n|-c|--lines|--bytes", t):
                return None
        na = _nonopt(args)
        files = [w for w in na if not re.fullmatch(r"[+-]?\d+[kKmMbB]*", w.text)]
        if len(files) == 1 and not stdin:
            return files[0]
        if not files and len(stdin) == 1:
            return stdin[0]
        return None
    if verb == "sed" and not any(w.text.startswith("--in-place") or _cluster_has(w.text, "i", "efl") for w in args):
        if not sed_delete_only(args):
            return None
        na = _nonopt(args)
        escripts = set()                                  # words that are -e SCRIPT values, not files
        for k, w in enumerate(args):
            if w.text in ("-e", "--expression") and k + 1 < len(args):
                escripts.add(id(args[k + 1]))
        if escripts:
            files = [w for w in na if id(w) not in escripts]
        else:
            files = na[1:]
        if len(files) == 1 and not stdin:
            return files[0]
        if not files and len(stdin) == 1:
            return stdin[0]
    return None


def command_targets(words, redirs):
    """[(Word, replaces?)] this one simple command writes to: real output-redirect targets + file args of known
    writing verbs. replaces? = the write truncates/replaces the file rather than appending to it."""
    tg = [(w, op in _REPLACE_REDIRS) for op, w in redirs
          if op in _OUT_REDIRS or (op == ">&" and not re.fullmatch(r"\d*-?", w.text))]
    ws = strip_wrappers(words)
    if not ws:
        return tg
    verb, args = os.path.basename(ws[0].text), ws[1:]
    texts = [w.text for w in args]
    if verb == "tee":
        app = any(t == "--append" or (t.startswith("-") and not t.startswith("--") and "a" in t) for t in texts)
        tg += [(w, not app) for w in _nonopt(args)]
    elif verb == "sed":
        if any(w.text.startswith("--in-place") or _cluster_has(w.text, "i", "efl") for w in args):
            tg += [(w, False) for w in _nonopt(args)]
    elif verb in ("perl", "ruby"):
        stops = "eExMmIFVdDC" if verb == "perl" else "eExrIFCKTW"      # options that take the REST of the cluster as a value
        if any(_cluster_has(w.text, "i", stops) for w in args):
            tg += [(w, False) for w in _nonopt(args)]
    elif verb in ("awk", "gawk", "mawk"):
        if "-iinplace" in texts or "--include=inplace" in texts or ("-i" in texts and "inplace" in texts) \
                or ("--include" in texts and "inplace" in texts):
            tg += [(w, False) for w in _nonopt(args)]
    elif verb in ("cp", "mv", "install", "ln", "rsync", "scp"):
        if not any(w.text.startswith("--target-directory") or _cluster_has(w.text, "t", "") for w in args):
            na = _nonopt(args)
            if len(na) >= 2:
                tg.append((na[-1], True))
    elif verb == "dd":
        tg += [(Word(w.text[3:], w.var), True) for w in args if w.text.startswith("of=")]
    elif verb.lower() in ("add-content",):
        tg += [(w, False) for w in _nonopt(args)]
    elif verb.lower() in ("set-content", "out-file"):
        tg += [(w, True) for w in _nonopt(args)]
    elif verb in ("sponge", "patch"):
        na = _nonopt(args)
        tg += [(w, True) for w in (na if verb == "sponge" else na[:1])]
    elif verb == "truncate":
        sz = _trunc_size(args)
        tg += [(w, bool(sz and sz[1])) for w in _nonopt(args)]
    elif verb in ("curl", "wget"):
        for k, w in enumerate(args):
            t = w.text
            if t in ("-o", "--output", "-O", "--output-document") and k + 1 < len(args) and (verb == "curl") == (t in ("-o", "--output")):
                tg.append((args[k + 1], True))
            elif t.startswith("--output=") or t.startswith("--output-document="):
                tg.append((Word(t.split("=", 1)[1], w.var), True))
            elif t.startswith("-") and not t.startswith("--") and k + 1 < len(args):
                last = t[-1]
                if (verb == "curl" and last == "o") or (verb == "wget" and last == "O"):
                    tg.append((args[k + 1], True))
    elif verb == "git":
        k = 0
        while k < len(args) and args[k].text.startswith("-"):
            k += 2 if args[k].text in ("-C", "-c", "--git-dir", "--work-tree") else 1
        sub = args[k].text if k < len(args) else ""
        rest = args[k + 1:]
        if sub in ("checkout", "restore"):
            t2 = [w.text for w in rest]
            if "--" in t2:
                tg += [(w, True) for w in rest[t2.index("--") + 1:]]
            elif sub == "restore":
                tg += [(w, True) for w in _nonopt(rest)]
    return tg


def expand(word, env=None):
    """Absolute or relative path text with ~ / $HOME / the command's own assignments / $(mktemp ...) expanded;
    None if another variable keeps it unresolvable."""
    t = re.sub(r"^~(?=/|$)", HOME, word.text)
    if word.var or "$" in t or "`" in t:
        t = _sub_home(t)
        t = re.sub(r"\$\(\s*mktemp[^)]*\)|`\s*mktemp[^`]*`", SCRATCH, t)
        t = re.sub(r"\$\{(\w+)\}|\$(\w+)", lambda m: (env or {}).get(m.group(1) or m.group(2), m.group(0)), t)
        if "$" in t or "`" in t:
            return None
    return t


_ASSIGN_RX = re.compile(r"""(?:^|[;&|(\s])(?:export\s+)?([A-Za-z_]\w*)=(\"?\$\(\s*mktemp[^)]*\)\"?|\"?`\s*mktemp[^`]*`\"?|"[^"]*"|'[^']*'|[^\s;&|()]*)""")


def scan_vars(command):
    """{name: value} for simple NAME=value assignments in the command; a mktemp result maps to SCRATCH."""
    env = {}
    for m in _ASSIGN_RX.finditer(command):
        name, val = m.group(1), m.group(2)
        if re.match(r"""^"?(?:\$\(|`)\s*mktemp""", val):
            env[name] = SCRATCH
            continue
        v = _sub_home(re.sub(r"^~(?=/|$)", HOME, val.strip("\"'")))
        v = re.sub(r"\$\{(\w+)\}|\$(\w+)", lambda x: env.get(x.group(1) or x.group(2), x.group(0)), v)
        if "$" not in v and "`" not in v:
            env[name] = v
    return env


def resolve_path(word, cur, env):
    p = expand(word, env)
    if p is None:
        return None
    if not os.path.isabs(p):
        if cur is None:
            return None
        p = os.path.join(cur, p)
    return os.path.realpath(os.path.normpath(p))


class Target(object):
    """One write the command performs: a path Word (kind "w") or executed python source (kind "py")."""
    __slots__ = ("kind", "word", "cwd", "est", "replace", "shrink", "find", "code")

    def __init__(self, kind, cwd, est, word=None, replace=False, shrink=None, find=None, code=None):
        self.kind, self.cwd, self.est, self.word = kind, cwd, est, word
        self.replace, self.shrink, self.find, self.code = replace, shrink, find, code


_SIZED_VERBS = ("cat", "cp", "mv", "install", "tee", "rsync", "scp", "sort", "tac", "head", "tail", "dd", "uniq")
_PYVERB = re.compile(r"^(?:python|pypy)[0-9.]*$")


def own_estimate(ws, redirs, hds, cur, env, skip):
    """Upper bound of the bytes this command can put into a file: its literal text + heredoc bodies + the size of the
    existing files a copying verb reads. Producers upstream of a pipe are added by the caller; a command whose output
    size is unrelated to its arguments (grep, python, a script) is counted by its text only."""
    est = sum(len(w.text.encode("utf-8")) for w in ws) + sum(len(b.encode("utf-8")) for h in hds for b in h)
    verb = os.path.basename(ws[0].text) if ws else ""
    if verb in _SIZED_VERBS:
        files = [w for w in ws[1:] if not w.text.startswith("-")]
        files += [Word(w.text[3:], w.var) for w in ws[1:] if w.text.startswith("if=")]
        files += [w for op, w in redirs if op == "<"]
        for w in files:
            p = resolve_path(w, cur, env)
            if p and p not in skip and os.path.isfile(p):
                est += size_of(p)
    return est


def bash_targets(command, cwd, depth=0, env=None, skip=frozenset()):
    """Yield a Target for every write, following cd and bash -c / eval / bash <<EOF."""
    env = scan_vars(command) if env is None else env
    stack, cur, chain, produced = [], cwd, 0, {}
    for item in simple_commands(lex(command)):
        if item[0] == "push":
            stack.append(cur); continue
        if item[0] == "pop":
            if stack:
                cur = stack.pop()
            continue
        words, redirs, hds, after_pipe = item[1], item[2], item[3], item[4]
        ws = strip_wrappers(words)
        verb = os.path.basename(ws[0].text) if ws else ""
        own = own_estimate(ws, redirs, hds, cur, env, skip)
        chain = (chain + own) if after_pipe else own
        shrink = None
        if verb == "sed" and any(w.text.startswith("--in-place") or _cluster_has(w.text, "i", "efl") for w in ws[1:]) \
                and sed_nongrow(ws[1:]):
            shrink = lambda real, size: True                       # delete-only or literal same-or-shorter s///: cannot grow
        elif verb in ("cp", "mv", "install", "rsync", "scp") and len(_nonopt(ws[1:])) >= 2:
            srcs = _nonopt(ws[1:])[:-1]
            keys = [resolve_path(w, cur, env) for w in srcs]
            sizes = [size_of(k) if (k and os.path.isfile(k)) else None for k in keys]

            def shrink(real, size, keys=keys, sizes=sizes):
                if keys and all(k is not None and k in produced and produced[k] == real for k in keys):
                    return True                                   # a grep -v / head / delete-only sed of the file itself
                return bool(sizes) and all(s is not None for s in sizes) and sum(sizes) < size
        for w, repl in command_targets(words, redirs):
            yield Target("w", cur, chain, word=w, replace=repl, shrink=shrink)
        if verb == "find":
            names, dirs, k = [], [], 1
            while k < len(ws) and not (ws[k].text.startswith("-") or ws[k].text in ("(", "!")):
                dirs.append(ws[k]); k += 1
            sub = None
            for k in range(1, len(ws)):
                t = ws[k].text
                if t in ("-name", "-iname") and k + 1 < len(ws):
                    names.append(ws[k + 1].text)
                if t in ("-exec", "-execdir", "-ok", "-okdir") and sub is None:
                    sub = []
                    for x in ws[k + 1:]:
                        if x.text in (";", "+"):
                            break
                        sub.append(x)
            if sub:
                for w, repl in command_targets(sub, []):
                    if "{}" in w.text:
                        yield Target("w", cur, chain, word=w, replace=repl, find=(names, dirs, cur, env))
        fin = filter_input(ws, redirs)
        if fin is not None:
            src = resolve_path(fin, cur, env)
            if src:
                for op, w in redirs:
                    if op == ">":
                        key = resolve_path(w, cur, env)
                        if key:
                            produced[key] = src
        if _PYVERB.match(verb):
            code = [hd for h in hds for hd in h]
            for k in range(1, len(ws) - 1):
                t = ws[k].text
                if t.startswith("-") and not t.startswith("--") and t.endswith("c"):
                    code.append(ws[k + 1].text)
                    break
            if code:
                yield Target("py", cur, chain, code="\n".join(code))
        if not ws:
            continue
        if verb in ("cd", "pushd"):
            a = [w for w in ws[1:] if w.text == "-" or not w.text.startswith("-")]
            if not a:
                cur = HOME
            else:
                p = None if a[0].text == "-" else expand(a[0], env)
                if p is None and a[0].text != "-":
                    names = re.findall(r"\$\{?(\w+)", a[0].text)
                    if names and not any(KBISH.search(n) for n in names) and all(SCRATCHY.search(n) for n in names):
                        p = SCRATCH
                if p is not None and not os.path.isabs(p):
                    p = os.path.join(cur, p) if cur else None
                cur = os.path.normpath(p) if p else None
        elif verb in ("bash", "sh", "zsh", "dash") and depth < 3:
            ran = False
            for k in range(1, len(ws)):
                t = ws[k].text
                if t.startswith("-") and not t.startswith("--") and t.endswith("c"):
                    if k + 1 < len(ws):
                        for x in bash_targets(ws[k + 1].text, cur, depth + 1, env, skip):
                            yield x
                    ran = True
                    break
            if not ran:                                           # bash <<EOF ... EOF
                for h in hds:
                    for body in h:
                        for x in bash_targets(body, cur, depth + 1, env, skip):
                            yield x
        elif verb == "eval" and depth < 3:
            for x in bash_targets(" ".join(w.text for w in ws[1:]), cur, depth + 1, env, skip):
                yield x


def _unresolved_hits(word, real):
    """The directory part has a variable or command substitution we could not resolve. Assume it can be the KB, except
    when the literal parts cannot match the path at all, or every variable is named like scratch space ($tmp, $SNAP)."""
    t = _sub_home(word.text)
    t = re.sub(r"^~(?=/|$)", HOME, t)
    names = re.findall(r"\$\{?(\w+)", t)
    pat = re.sub(r"\$\([^()]*\)|`[^`]*`|\$\{\w+\}|\$\w+", "*", t)
    if os.path.isabs(pat) or pat.startswith("*"):
        if not fnmatch.fnmatchcase(real, pat):
            return False
    if names and not any(KBISH.search(n) for n in names) and all(SCRATCHY.search(n) for n in names):
        return False
    return True


def target_hits(t, real, command, env):
    w = t.word
    if t.find is not None and "{}" in w.text:                   # find ... -exec <writer> {} + : the files are find's
        names, dirs, fcwd, fenv = t.find
        if names and not any(fnmatch.fnmatch(os.path.basename(real), n) or
                             fnmatch.fnmatch(os.path.basename(real).lower(), n.lower()) for n in names):
            return False
        if not dirs:
            dirs = [Word(".", False)]
        for d in dirs:
            p = resolve_path(d, fcwd, fenv)
            if p is None or real == p or real.startswith(p.rstrip(os.sep) + os.sep):
                return True
        return False
    base_w = os.path.basename(w.text)
    glob = bool(GLOBCH.search(base_w))
    if glob:
        if not fnmatch.fnmatchcase(os.path.basename(real), base_w):
            return False
    elif base_w != os.path.basename(real):
        return False
    p = expand(w, env)
    if p is None:
        return _unresolved_hits(w, real)
    if not os.path.isabs(p):
        if t.cwd is None:                 # after `cd $X` / `cd -`: unknown cwd, fall back to "names the KB dir"
            return os.path.basename(os.path.dirname(real)) in command
        p = os.path.join(t.cwd, p)
    p = os.path.normpath(p)
    if glob:
        return os.path.realpath(os.path.dirname(p)) == os.path.dirname(real)
    return os.path.realpath(p) == real


def bash_writes_capped(command, capped, cwd):
    """Return (rel, cur, cap, new) for the first capped file the command writes to and would leave over its cap, else
    None. A file already AT/over its cap refuses any recognised write that is not provably a shrink (the shell cannot be
    measured); a file under its cap refuses a write whose estimated result (existing size + text the command carries,
    heredoc bodies, files it copies) exceeds the cap. An archive-helper call writes nothing the parser can see, so it passes
    by itself; it no longer exempts a write chained after it (attack FA1)."""
    cands = []
    for real, (rel, cap) in capped.items():
        if os.path.basename(real) in command or GLOBCH.search(command):
            cands.append((real, rel, cap, size_of(real)))
    if not cands:
        return None
    env = scan_vars(command)
    targets = list(bash_targets(command, cwd, env=env, skip=frozenset(capped)))
    for real, rel, cap, cur in cands:
        for t in targets:
            if t.kind == "py":
                if not py_writes_target(t.code, real, t.cwd, command):
                    continue
            elif not target_hits(t, real, command, env):
                continue
            if t.shrink and t.shrink(real, cur):
                continue
            if cur >= cap:
                return rel, cur, cap, cur
            new = t.est if t.replace else cur + t.est
            if new > cap:
                return rel, cur, cap, new
    return None


# ---------------------------------------------------------------- main

def decide(data):
    tool = data.get("tool_name") or ""
    ti = data.get("tool_input") or {}
    sid = data.get("session_id") or ""
    cwd = data.get("cwd") or os.getcwd()
    if tool not in ("Write", "Edit", "MultiEdit", "Bash"):
        return None
    caps = load_caps()
    if not caps:
        return None
    if tool == "Bash":
        hit = bash_writes_capped(ti.get("command") or "", caps, cwd)
        if not hit:
            return None
        rel, cur, cap, new = hit
        return ("bash", rel, cur, cap, new, sid)
    p = ti.get("file_path")
    if not p or not isinstance(p, str):
        return None
    p = p if os.path.isabs(p) else os.path.join(cwd, p)
    real = os.path.realpath(p)
    if real not in caps:
        return None
    rel, cap = caps[real]
    try:
        with open(real, "rb") as f:
            data_b = f.read()
    except OSError:
        data_b = b""
    cur = len(data_b)
    new = edit_new_size(data_b, ti, tool)
    if new > cap and new > cur:
        return ("edit", rel, cur, cap, new, sid)
    return None


def main():
    try:
        data = json.load(sys.stdin)
        res = decide(data)
        if not res:
            return 0
        kind, rel, cur, cap, new, sid = res
        why = consume_override(sid)
        if why is not None:
            log("OVERRIDE\tsession=%s\t%s\tcur=%d\tcap=%d\tnew=%d\t%s\t%s" % (sid, rel, cur, cap, new, kind, why))
            return 0
        log("DENY\tsession=%s\t%s\tcur=%d\tcap=%d\tnew=%d\t%s" % (sid, rel, cur, cap, new, kind))
        deny(reason_text(rel, cur, cap, new, sid, bash=(kind == "bash")))
        return 0
    except Exception as ex:           # fail OPEN
        log("ERROR-FAILOPEN\t%s: %s" % (type(ex).__name__, ex))
        return 0


if __name__ == "__main__":
    sys.exit(main())
