#!/usr/bin/env python3
"""Kit lint: no identifier from any profile's denylist may appear under core/.

Usage:  lint.py [--core DIR] [--profiles DIR]
Exit:   0 no hits | 1 at least one hit | 2 usage or input error

Every non-empty, non-comment line of profiles/*/lint-denylist.txt is an identifier.
Every file under core/ is searched line by line, case-insensitively, and each hit
prints on stdout as  path:line: identifier  (the identifier as the denylist spells it).
A one-line summary goes to stderr.

Fails closed on its input. If no identifier could be loaded, if core/ holds no files,
or if a file could not be read, part of the job was not done, so the result is never a
clean 0. Symlinks are not followed (each one is named on stderr). UTF-16 files with a
byte-order mark are decoded; everything else is read as UTF-8 with replacement.
Standard library only.
"""
import argparse
import os
import sys

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_identifiers(profiles_dir):
    """Return (denylist paths, identifiers). Identifiers are deduplicated case-insensitively."""
    denylists, seen, idents = [], set(), []
    for name in sorted(os.listdir(profiles_dir)):
        path = os.path.join(profiles_dir, name, "lint-denylist.txt")
        if not os.path.isfile(path):
            continue
        denylists.append(path)
        with open(path, encoding="utf-8-sig") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                key = line.casefold()
                if key not in seen:
                    seen.add(key)
                    idents.append(line)
    return denylists, idents


def decode(data):
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    return data.decode("utf-8", errors="replace")


SKIP_DIRS = ("__pycache__",)  # same list render.py uses for the kb tree
SKIP_SUFFIXES = (".pyc", ".pyo")


def scan(core_dir, idents):
    """Return (files scanned, unreadable [(path, error)], hits [(path, line number, identifier)])."""
    folded = [(ident, ident.casefold()) for ident in idents]
    hits, unreadable, nfiles = [], [], 0
    for root, dirs, files in os.walk(core_dir):
        dirs.sort()
        for d in list(dirs):
            full = os.path.join(root, d)
            if d in SKIP_DIRS:  # compiled bytecode carries the absolute source path, which is an identifier
                dirs.remove(d)
                continue
            if os.path.islink(full):
                print("lint: not following symlinked dir %s" % full, file=sys.stderr)
                dirs.remove(d)
        for fn in sorted(files):
            if fn.endswith(SKIP_SUFFIXES):
                continue
            path = os.path.join(root, fn)
            if os.path.islink(path):
                print("lint: not following symlink %s" % path, file=sys.stderr)
                continue
            try:
                with open(path, "rb") as fh:
                    text = decode(fh.read())
            except OSError as exc:
                unreadable.append((path, exc))
                continue
            nfiles += 1
            for lineno, line in enumerate(text.split("\n"), 1):
                low = line.casefold()
                for ident, fold in folded:
                    if fold in low:
                        hits.append((path, lineno, ident))
    return nfiles, unreadable, hits


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Fail if any profile's lint-denylist identifier appears under core/. "
                    "Exit 0 clean, 1 hit, 2 usage or input error.")
    ap.add_argument("--core", default=os.path.join(KIT, "core"),
                    help="directory to scan (default: kit/core)")
    ap.add_argument("--profiles", default=os.path.join(KIT, "profiles"),
                    help="directory holding <name>/lint-denylist.txt (default: kit/profiles)")
    args = ap.parse_args(argv)  # argparse exits 2 on a usage error

    for flag, path in (("--core", args.core), ("--profiles", args.profiles)):
        if not os.path.isdir(path):
            print("lint: %s is not a directory: %s" % (flag, path), file=sys.stderr)
            return 2
    try:
        denylists, idents = load_identifiers(args.profiles)
    except (OSError, UnicodeError) as exc:
        print("lint: cannot read a denylist: %s" % exc, file=sys.stderr)
        return 2
    if not idents:
        print("lint: no identifiers loaded from %d denylist file(s) under %s; nothing was checked, "
              "so it will not report clean" % (len(denylists), args.profiles), file=sys.stderr)
        return 2

    nfiles, unreadable, hits = scan(args.core, idents)
    for path, lineno, ident in hits:
        print("%s:%d: %s" % (path, lineno, ident))
    for path, exc in unreadable:
        print("lint: cannot read %s: %s" % (path, exc), file=sys.stderr)
    print("lint: scanned %d file(s) under %s against %d identifier(s) from %d denylist(s): %d hit(s)"
          % (nfiles, args.core, len(idents), len(denylists), len(hits)), file=sys.stderr)
    if hits:
        return 1
    if unreadable:
        return 2
    if nfiles == 0:
        print("lint: no files found under %s; nothing was checked, so it will not report clean"
              % args.core, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
