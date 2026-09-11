#!/usr/bin/env python3
"""Proves tools/ast_audit.py can actually FAIL.

    python3 tools/audit_selftest.py

An audit that cannot fail is decoration, and a green run from one is worse than
no run at all because it buys false confidence. This injects each bug class the
audit claims to catch — one at a time, into a COPY of the contracts — and
asserts the audit reports it. Then it reverts and asserts the audit goes clean
again, so a scanner that simply fires on everything is caught too.

The nine mutations are the nine rejections, restated as code:

    write-then-raise      a counter incremented before a revert
    frozen-state          a mutator with its _mutable gate removed
    payable-revert        a payable method raising instead of refunding
    str-replace           a call the runner rejects
    nondet-self           a closure capturing self
    unsnapshotted-term    a frozen term read from the live config
    owner-reach           an owner method touching the verification table
    provenance (axis)     the validator comparing the level alone, leaving the
                          counts it is checked against unagreed
    provenance (apply)    the level derived from the counts instead of checked
                          against them

The last two are THIS project's rejection, and they are injected separately on
purpose: either gate alone would have stopped the forgery, so a self-test that
broke both at once could not tell a working pair of gates from one working gate
carrying a dead one.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (what the line prints, what the audit must print, anchor, replacement)
MUTATIONS = [
	("write-then-raise", "write-then-raise",
	 '\t\tself.paused = True\n\t\treturn json.dumps({"ok": True, "paused": True})',
	 '\t\tself.paused = True\n\t\tif False:\n\t\t\traise gl.vm.UserError("x")\n\t\treturn json.dumps({"ok": True, "paused": True})'),
	("frozen-state", "frozen-state",
	 '\t\tif not self._mutable(record):\n\t\t\treturn json.dumps({\n\t\t\t\t"ok": False,\n\t\t\t\t"reason": "verification is already " + str(record.status),',
	 '\t\tif True:\n\t\t\tpass\n\t\tif False:\n\t\t\treturn json.dumps({\n\t\t\t\t"ok": False,\n\t\t\t\t"reason": "verification is already " + str(record.status),'),
	("payable-revert", "payable-revert",
	 '\t\tif self.paused:\n\t\t\treturn self._reject(sender, value, "contract is paused")',
	 '\t\tif self.paused:\n\t\t\traise gl.vm.UserError("contract is paused")'),
	("str-replace", "str-replace",
	 'def _pct(value: str) -> str:',
	 'def _pct(value: str) -> str:\n\tvalue = str(value).replace("x", "y")'),
	("nondet-self", "nondet-self",
	 '\tdef leader_fn() -> dict:\n\t\treturn _evaluate(user, lang)',
	 '\tdef leader_fn() -> dict:\n\t\tself.paused\n\t\treturn _evaluate(user, lang)'),
	("unsnapshotted-term", "unsnapshotted-term",
	 '\t\tdue = int(record.requested_at) + int(record.resolve_window)',
	 '\t\tdue = int(record.requested_at) + int(self.resolve_window)'),
	("owner-reach", "owner-reach",
	 '\t\tself.paused = True\n\t\treturn json.dumps({"ok": True, "paused": True})',
	 '\t\tself.paused = True\n\t\tself.verifications\n\t\treturn json.dumps({"ok": True, "paused": True})'),
	# The rejected consensus bug, gate 1: the validator compares the level and
	# nothing else, so the repo_count and total_bytes the level is checked
	# against are whatever the leader felt like sending.
	("provenance — the validator compares the bare level", "provenance",
	 '\t\tmine = _compare_key(leader_fn())\n\t\ttheirs = _compare_key(leader_result.calldata)',
	 '\t\tmine = _axis_of(leader_fn())\n\t\ttheirs = _axis_of(leader_result.calldata)'),
	# The same bug, gate 2: _apply derives the stored level from the counts
	# rather than checking the agreed level against them.
	("provenance — _apply derives the level instead of checking it", "provenance",
	 '\t\t\trecomputed = _level_for(repo_count, total_bytes)\n\t\t\tif recomputed != level:',
	 '\t\t\tlevel = _level_for(repo_count, total_bytes)\n\t\t\tif False:'),
]

failures = []
with tempfile.TemporaryDirectory() as tmp:
	work = Path(tmp)
	for sub in ("contracts", "build", "tools"):
		(work / sub).mkdir()
	for f in (ROOT / "contracts").glob("*.py"):
		shutil.copy(f, work / "contracts" / f.name)
	for f in (ROOT / "build").glob("*.min.py"):
		shutil.copy(f, work / "build" / f.name)
	shutil.copy(ROOT / "tools" / "ast_audit.py", work / "tools" / "ast_audit.py")

	target = work / "contracts" / "SkillVerify.py"
	base = target.read_text(encoding="utf8")

	print("audit self-test — each bug class injected, one at a time")
	print("=" * 70)
	for label, needle, old, new in MUTATIONS:
		if old not in base:
			print(f"  ??   {label}: mutation anchor no longer present in the source")
			failures.append(label + " (anchor missing — the self-test has gone stale)")
			continue
		target.write_text(base.replace(old, new, 1), encoding="utf8")
		result = subprocess.run([sys.executable, "tools/ast_audit.py"], cwd=work,
			capture_output=True, text=True)
		caught = needle in result.stdout and result.returncode != 0
		print(f"  {'ok  ' if caught else 'MISS'} the audit catches an injected {label}")
		if not caught:
			failures.append(label)

	target.write_text(base, encoding="utf8")
	result = subprocess.run([sys.executable, "tools/ast_audit.py"], cwd=work,
		capture_output=True, text=True)
	clean = result.returncode == 0
	print(f"  {'ok  ' if clean else 'FAIL'} and goes clean again when the mutation is reverted")
	if not clean:
		failures.append("the audit does not go clean on unmutated sources")

print("=" * 70)
if failures:
	print(f"{len(failures)} SCAN(S) DO NOT WORK: {', '.join(failures)}")
	sys.exit(1)
print(f"all {len(MUTATIONS)} scans demonstrably fire, and only on the bug.")
