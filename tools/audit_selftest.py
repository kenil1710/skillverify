#!/usr/bin/env python3
"""Proves tools/ast_audit.py can actually FAIL.

    python3 tools/audit_selftest.py

An audit that cannot fail is decoration, and a green run from one is worse than
no run at all because it buys false confidence. This injects each bug class the
audit claims to catch — one at a time, into a COPY of the contracts — and
asserts the audit reports it. Then it reverts and asserts the audit goes clean
again, so a scanner that simply fires on everything is caught too.

The eleven mutations are the rejections, restated as code:

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
    unbound-claimant (a)  the oracle stops publishing the binding, so no
                          consumer can read it
    unbound-claimant (b)  the consumer pays whoever quotes the username, which
                          is the bug the reviewer found

The provenance pair is THIS project's first rejection, and they are injected
separately on purpose: either gate alone would have stopped the forgery, so a
self-test that broke both at once could not tell a working pair of gates from
one working gate carrying a dead one. The unbound-claimant pair is the second
rejection, and is split across both contracts for the same reason — the oracle
publishing a binding nobody checks and a consumer checking a binding nobody
publishes are different failures with the same symptom.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ORACLE = "SkillVerify.py"
CONSUMER = "SkillConsumer.py"

# (what the line prints, what the audit must print, which file, anchor, replacement)
MUTATIONS = [
	("write-then-raise", "write-then-raise", ORACLE,
	 '\t\tself.paused = True\n\t\treturn json.dumps({"ok": True, "paused": True})',
	 '\t\tself.paused = True\n\t\tif False:\n\t\t\traise gl.vm.UserError("x")\n\t\treturn json.dumps({"ok": True, "paused": True})'),
	("frozen-state", "frozen-state", ORACLE,
	 '\t\tif not self._mutable(record):\n\t\t\treturn json.dumps({\n\t\t\t\t"ok": False,\n\t\t\t\t"reason": "verification is already " + str(record.status),',
	 '\t\tif True:\n\t\t\tpass\n\t\tif False:\n\t\t\treturn json.dumps({\n\t\t\t\t"ok": False,\n\t\t\t\t"reason": "verification is already " + str(record.status),'),
	("payable-revert", "payable-revert", ORACLE,
	 '\t\tif self.paused:\n\t\t\treturn self._reject(sender, value, "contract is paused")',
	 '\t\tif self.paused:\n\t\t\traise gl.vm.UserError("contract is paused")'),
	("str-replace", "str-replace", ORACLE,
	 'def _pct(value: str) -> str:',
	 'def _pct(value: str) -> str:\n\tvalue = str(value).replace("x", "y")'),
	("nondet-self", "nondet-self", ORACLE,
	 '\tdef leader_fn() -> dict:\n\t\treturn _evaluate(user, lang)',
	 '\tdef leader_fn() -> dict:\n\t\tself.paused\n\t\treturn _evaluate(user, lang)'),
	("unsnapshotted-term", "unsnapshotted-term", ORACLE,
	 '\t\tdue = int(record.requested_at) + int(record.resolve_window)',
	 '\t\tdue = int(record.requested_at) + int(self.resolve_window)'),
	("owner-reach", "owner-reach", ORACLE,
	 '\t\tself.paused = True\n\t\treturn json.dumps({"ok": True, "paused": True})',
	 '\t\tself.paused = True\n\t\tself.verifications\n\t\treturn json.dumps({"ok": True, "paused": True})'),
	# The rejected consensus bug, gate 1: the validator compares the level and
	# nothing else, so the repo_count and total_bytes the level is checked
	# against are whatever the leader felt like sending.
	("provenance — the validator compares the bare level", "provenance", ORACLE,
	 '\t\tmine = _compare_key(leader_fn())\n\t\ttheirs = _compare_key(leader_result.calldata)',
	 '\t\tmine = _axis_of(leader_fn())\n\t\ttheirs = _axis_of(leader_result.calldata)'),
	# The same bug, gate 2: _apply derives the stored level from the counts
	# rather than checking the agreed level against them.
	("provenance — _apply derives the level instead of checking it", "provenance", ORACLE,
	 '\t\t\trecomputed = _level_for(repo_count, total_bytes)\n\t\t\tif recomputed != level:',
	 '\t\t\tlevel = _level_for(repo_count, total_bytes)\n\t\t\tif False:'),
	# The reviewer's rejection, oracle half: the binding stops riding on the
	# document, so every consumer reads "" and either refuses everything or —
	# if it were written to fail open — pays everybody.
	("unbound-claimant — the oracle stops publishing the binding", "unbound-claimant", ORACLE,
	 '\t\t\t"identity_owner": self._identity_owner(str(record.github_username)),',
	 '\t\t\t"unbound": "",'),
	# The same rejection, consumer half: the gate stops comparing the binding to
	# the caller, which is exactly the code that shipped.
	("unbound-claimant — the consumer pays whoever asks", "unbound-claimant", CONSUMER,
	 '\t\tif owner != claimant or _is_zero_address(claimant):',
	 '\t\tif False:'),
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

	# Both contracts are mutable now: a binding the oracle publishes and the
	# consumer never checks is as broken as the reverse, and the two live in
	# different files.
	bases = {name: (work / "contracts" / name).read_text(encoding="utf8")
		for name in (ORACLE, CONSUMER)}

	def restore():
		for name, text in bases.items():
			(work / "contracts" / name).write_text(text, encoding="utf8")

	print("audit self-test — each bug class injected, one at a time")
	print("=" * 70)
	for label, needle, filename, old, new in MUTATIONS:
		base = bases[filename]
		if old not in base:
			print(f"  ??   {label}: mutation anchor no longer present in {filename}")
			failures.append(label + " (anchor missing — the self-test has gone stale)")
			continue
		restore()
		(work / "contracts" / filename).write_text(base.replace(old, new, 1), encoding="utf8")
		result = subprocess.run([sys.executable, "tools/ast_audit.py"], cwd=work,
			capture_output=True, text=True)
		caught = needle in result.stdout and result.returncode != 0
		print(f"  {'ok  ' if caught else 'MISS'} the audit catches an injected {label}")
		if not caught:
			failures.append(label)

	restore()
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
