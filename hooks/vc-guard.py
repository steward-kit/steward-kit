#!/usr/bin/env python3
"""vc-guard.py - PostToolUse hook for Write|Edit|NotebookEdit. Rule: everything we build is in git.

Reads hook JSON on stdin. If the file written is inside a git work tree (gitignored paths included:
we only look for a .git ancestor), or under an exempt prefix, exit 0 silently. Otherwise exit 2 with a
short stderr message for Claude. FAILS OPEN (exit 0) on any internal error. No network, no subprocess:
one os.path.exists walk.

Config (env, all optional):
  KIT_VC_EXEMPT    colon-separated extra exempt path prefixes (default none)
  VC_CONF_DIR      directory holding exempt.conf (default ~/.config/kit-vc); rows are
                   "local<TAB>/abs/prefix<TAB>reason"
  KIT_VC_ADOPT_CMD command suggested in the message (default "git init")
"""
import json
import os
import re
import sys

HOME = os.path.expanduser("~")
ME = os.path.realpath(__file__)
BUILTIN_EXEMPT = ["/tmp", "/var/tmp", "/proc", "/dev", HOME + "/.cache", HOME + "/.local/state", HOME + "/.claude"]
BUILTIN_EXEMPT += [p for p in (os.environ.get("KIT_VC_EXEMPT") or "").split(":") if p]
ADOPT = os.environ.get("KIT_VC_ADOPT_CMD") or "git init"


def exempt_prefixes():
    """built-ins + local rows of exempt.conf (split on tab RUNS). An empty, relative, '/', HOME or any
    ANCESTOR of HOME prefix is refused (it would exempt everything), so a stray tab can never switch
    the guard off."""
    out = list(BUILTIN_EXEMPT)
    conf = os.environ.get("VC_CONF_DIR") or os.path.join(HOME, ".config", "kit-vc")
    try:
        with open(os.path.join(conf, "exempt.conf")) as f:
            for line in f:
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                p = re.split(r"\t+", line.strip())
                if len(p) < 2 or p[0] != "local":
                    continue
                pre = os.path.expanduser(p[1].strip())
                if not pre or not os.path.isabs(pre):
                    continue
                pre = os.path.normpath(pre).rstrip("/")
                if pre in ("", "/") or under(HOME, pre):
                    continue
                out.append(pre)
    except OSError:
        pass
    return out


def under(path, prefix):
    return path == prefix or path.startswith(prefix.rstrip("/") + "/")


def in_work_tree(path):
    d = os.path.dirname(path)
    while True:
        if os.path.exists(os.path.join(d, ".git")):
            return True
        nd = os.path.dirname(d)
        if nd == d:
            return False
        d = nd


def top_project(path):
    rel = os.path.relpath(path, HOME) if under(path, HOME) else None
    if rel is None:
        return os.path.dirname(path)
    parts = rel.split("/")
    if parts[0] == "projects" and len(parts) > 2:
        return "~/projects/" + parts[1]
    return "~/" + parts[0] if len(parts) > 1 else "~"


def main():
    try:
        data = json.load(sys.stdin)
        ti = data.get("tool_input") or {}
        p = ti.get("file_path") or ti.get("notebook_path")
        if not p or not isinstance(p, str):
            return 0
        if not os.path.isabs(p):
            p = os.path.join(data.get("cwd") or os.getcwd(), p)
        p = os.path.normpath(p)
        cands = {p, os.path.realpath(p)}
        for c in cands:
            if any(under(c, e) for e in exempt_prefixes()) or in_work_tree(c):
                return 0
        sys.stderr.write(
            "[vc-guard.py: %s - local PostToolUse hook, version-control rule]\n"
            "NOT UNDER VERSION CONTROL: %s. Rule: everything we build goes in git. "
            "Run: %s in %s (or add the path to exempt.conf with a reason).\n" % (ME, p, ADOPT, top_project(p)))
        return 2
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
