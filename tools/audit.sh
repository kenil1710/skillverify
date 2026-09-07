#!/usr/bin/env bash
# The full pre-submission gate. Everything, in the order that fails fastest.
#
#   bash tools/audit.sh
#
# The artifact size ceiling is checked FIRST because it is the constraint that
# decides whether the project can ship at all; there is no point knowing the
# tests pass on something Bradbury will refuse.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "══ 1. build the artifacts"
bash tools/build.sh | grep -E "bytes|passed" | sed 's/^/  /'

echo
echo "══ 2. lint"
for f in contracts/SkillVerify.py contracts/SkillConsumer.py build/SkillVerify.min.py build/SkillConsumer.min.py; do
  printf "  %-34s " "$f"
  "$HOME/.local/bin/genvm-lint" check "$f" 2>&1 | grep -qE "Validation passed" && echo "ok" || { echo "FAIL"; exit 1; }
done

echo
echo "══ 3. AST audit — every bug class, by parsing"
python3 tools/ast_audit.py | tail -3 | sed 's/^/  /'

echo
echo "══ 4. audit self-test — proves the audit can fail"
python3 tools/audit_selftest.py | tail -2 | sed 's/^/  /'

echo
echo "══ 5. offline suite"
python3 test/test_logic.py 2>&1 | tail -3 | sed 's/^/  /'

echo
echo "══ 6. checksums"
python3 - <<'PY' | sed 's/^/  /'
import hashlib, json, os
d = json.load(open("deployments.json"))
for art, meta in d["artifacts"].items():
    b = open(art, "rb").read()
    digest = hashlib.sha256(b).hexdigest()
    match = "ok  " if digest == meta.get("sha256") else "STALE"
    print(f"{match} {len(b):>7,} bytes  {art}  {digest[:16]}…")
PY

echo
echo "══ all gates passed"
