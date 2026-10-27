#!/usr/bin/env bash
# Lint controls. Exit codes are judged explicitly, so there is no set -e.
#   Control 1 (must pass):   the real tree is clean, and the check was not vacuous.
#   Control 2 (must fail):   identifiers planted in a copy of core/ are caught, case-insensitively.
#   Control 3 (must refuse): with no identifiers to check, lint exits 2 and never reports a clean 0.
#   Control 4 (must skip):   compiled bytecode (__pycache__/, *.pyc) is not scanned; a planted .md beside it still is.
set -u -o pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
kit="$(cd "$here/../.." && pwd)"
lint="$kit/lint/lint.py"
failures=0

tmp="$(mktemp -d)" || { echo "FAIL  cannot create a temp dir"; exit 1; }
trap 'rm -rf -- "$tmp"' EXIT

pass() { echo "PASS  $1"; }
fail() { echo "FAIL  $1"; failures=$((failures + 1)); }
indent() { sed 's/^/        /'; }

# Control 1: the real tree must pass, with at least one identifier actually loaded.
out="$(python3 "$lint" 2>"$tmp/c1.err")"; rc=$?
if [ "$rc" -eq 0 ] && [ -z "$out" ] && grep -Eq 'against [1-9][0-9]* identifier' "$tmp/c1.err"; then
  pass "control 1: real tree is clean (exit 0, no hits)"
  tail -n 1 "$tmp/c1.err" | indent
else
  fail "control 1: expected exit 0, no hits and a non-empty identifier set; got exit $rc, hits: $([ -z "$out" ] && echo none || echo present), identifier count in summary: $(grep -Eq 'against [1-9][0-9]* identifier' "$tmp/c1.err" && echo ok || echo MISSING)"
  { echo "stdout:"; echo "$out"; echo "stderr:"; cat "$tmp/c1.err"; } | indent
fi

# Control 2: plant LABCORP-ZETA (exact case) and Lab-Host-9 (mixed case) in a copy of core/.
if cp -R "$kit/core" "$tmp/core"; then
  printf 'first line\nplanted: LABCORP-ZETA here\n' > "$tmp/core/planted-a.md"
  mkdir -p "$tmp/core/agents"
  printf 'x\ny\nmixed case: Lab-Host-9 here\n' > "$tmp/core/agents/planted-b.md"
  out="$(python3 "$lint" --core "$tmp/core" 2>"$tmp/c2.err")"; rc=$?
  want_a="$tmp/core/planted-a.md:2: LABCORP-ZETA"
  want_b="$tmp/core/agents/planted-b.md:3: lab-host-9"
  ok=1
  [ "$rc" -eq 1 ] || ok=0
  grep -Fxq -- "$want_a" <<<"$out" || ok=0
  grep -Fxq -- "$want_b" <<<"$out" || ok=0
  [ "$(grep -c . <<<"$out")" -eq 2 ] || ok=0   # exactly the two planted hits, nothing else
  if [ "$ok" -eq 1 ]; then
    pass "control 2: planted identifiers caught (exit 1, both hits printed)"
    echo "$out" | sed "s#$tmp#<tmp>#" | indent
  else
    fail "control 2: expected exit 1 and exactly the two planted hits, got exit $rc"
    { echo "stdout:"; echo "$out"; echo "stderr:"; cat "$tmp/c2.err"; } | indent
  fi
else
  fail "control 2: could not copy core/ to the temp dir"
fi

# Control 3: no denylist identifiers at all. A clean 0 here would be a vacuous pass.
mkdir "$tmp/noprofiles"
out="$(python3 "$lint" --profiles "$tmp/noprofiles" 2>"$tmp/c3.err")"; rc=$?
if [ "$rc" -eq 2 ] && [ -z "$out" ]; then
  pass "control 3: empty denylist set is refused (exit 2, not a clean 0)"
else
  fail "control 3: expected exit 2 with an empty denylist set, got exit $rc"
  { echo "stdout:"; echo "$out"; echo "stderr:"; cat "$tmp/c3.err"; } | indent
fi

# Control 4: bytecode carries the absolute source path (an identifier) and is gitignored; lint must skip it,
# and the check must not be vacuous: a planted .md beside it is still the one hit.
if cp -R "$kit/core" "$tmp/core4"; then
  mkdir -p "$tmp/core4/tools/__pycache__"
  printf 'LABCORP-ZETA in bytecode\n' > "$tmp/core4/tools/__pycache__/x.cpython-313.pyc"
  printf 'LABCORP-ZETA in a loose pyc\n' > "$tmp/core4/tools/loose.pyc"
  printf 'planted: LABCORP-ZETA here\n' > "$tmp/core4/planted-c.md"
  out="$(python3 "$lint" --core "$tmp/core4" 2>"$tmp/c4.err")"; rc=$?
  want_c="$tmp/core4/planted-c.md:1: LABCORP-ZETA"
  ok=1
  [ "$rc" -eq 1 ] || ok=0
  grep -Fxq -- "$want_c" <<<"$out" || ok=0
  [ "$(grep -c . <<<"$out")" -eq 1 ] || ok=0   # the .md only; neither pyc is reported
  grep -q 'pyc' <<<"$out" && ok=0
  if [ "$ok" -eq 1 ]; then
    pass "control 4: bytecode skipped, planted .md beside it still caught (exit 1, one hit)"
    echo "$out" | sed "s#$tmp#<tmp>#" | indent
  else
    fail "control 4: expected exit 1 and only the planted .md hit, got exit $rc"
    { echo "stdout:"; echo "$out"; echo "stderr:"; cat "$tmp/c4.err"; } | indent
  fi
else
  fail "control 4: could not copy core/ to the temp dir"
fi

if [ "$failures" -eq 0 ]; then
  echo "RESULT: all 4 lint controls behaved"
  exit 0
fi
echo "RESULT: $failures of 4 lint controls misbehaved"
exit 1
