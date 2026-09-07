#!/usr/bin/env python3
"""The pre-submission AST audit. Every bug class a previous project was
rejected for, checked by parsing the file rather than by remembering.

    python3 tools/ast_audit.py

Nine scans. Each one is a rejection somebody actually wrote, turned into
something a machine can refuse to let past:

  1. WRITE-THEN-RAISE       — a counter incremented before a revert
                               (PackageGuard / Joaquin)
  2. FROZEN-STATE MUTATION  — a write reachable after a terminal status
                               (PackageGuard / Joaquin)
  3. UNSNAPSHOTTED TERMS    — a per-record term read from the live config
                               instead of the record (PredictStake / Pavel)
  4. PAYABLE REVERT         — a raise reachable from a payable method
                               (ClaimStake / Pavel)
  5. OWNER REACH            — an owner method that can touch a user record
  6. STORED-FIELD PROVENANCE— a stored field not recomputed from evidence
  7. str.replace()          — rejected by the runner
  8. SELF IN A NONDET CLOSURE — pickles storage, kills the leader at 0s
  9. ARTIFACT SIZE          — the ceiling that decides whether this deploys

Exit code is the number of findings, so it can gate a build.
"""

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = [ROOT / "contracts" / "SkillVerify.py", ROOT / "contracts" / "SkillConsumer.py"]
ARTIFACTS = [ROOT / "build" / "SkillVerify.min.py", ROOT / "build" / "SkillConsumer.min.py"]
ARTIFACT_BUDGET = 48_000

findings = []
checks = 0


def finding(scan, path, line, message):
	findings.append(f"{scan}: {path.name}:{line} — {message}")


def ok(label, detail=""):
	global checks
	checks += 1
	print(f"  ok   {label}" + (f"  ({detail})" if detail else ""))


def bad(label, detail=""):
	global checks
	checks += 1
	print(f"  FAIL {label}" + (f"  ({detail})" if detail else ""))


def classes(tree):
	return [n for n in tree.body if isinstance(n, ast.ClassDef)]


def methods(cls):
	return [n for n in cls.body if isinstance(n, ast.FunctionDef)]


def decorators(fn):
	return [ast.unparse(d) for d in fn.decorator_list]


def is_state_write(node):
	targets = []
	if isinstance(node, ast.Assign):
		targets = node.targets
	elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
		targets = [node.target]
	else:
		return False
	for t in targets:
		base = t
		while isinstance(base, ast.Subscript):
			base = base.value
		if isinstance(base, ast.Attribute):
			return True
	return False


def writes_anywhere(body):
	for stmt in body:
		if is_state_write(stmt):
			return True
		for field in ("body", "orelse", "finalbody"):
			inner = getattr(stmt, field, None)
			if isinstance(inner, list) and writes_anywhere(inner):
				return True
		for h in getattr(stmt, "handlers", []) or []:
			if writes_anywhere(h.body):
				return True
	return False


def raises_after_write(fn):
	"""SCAN 1. Every state write with a `raise` reachable AFTER it."""
	hits = []

	def scan(body, seen):
		for stmt in body:
			if is_state_write(stmt):
				seen = True
				continue
			if isinstance(stmt, ast.Raise) and seen:
				hits.append(stmt.lineno)
				continue
			for field in ("body", "orelse", "finalbody"):
				inner = getattr(stmt, field, None)
				if isinstance(inner, list):
					scan(inner, seen)
			for h in getattr(stmt, "handlers", []) or []:
				scan(h.body, seen)
			if any(writes_anywhere(getattr(stmt, f, []) or []) for f in ("body", "orelse", "finalbody")):
				seen = True

	scan(fn.body, False)
	return hits


def calls_named(fn, name):
	for node in ast.walk(fn):
		if isinstance(node, ast.Call):
			f = node.func
			if isinstance(f, ast.Attribute) and f.attr == name:
				return True
			if isinstance(f, ast.Name) and f.id == name:
				return True
	return False


def record_writes(fn):
	out = []
	for node in ast.walk(fn):
		targets = []
		if isinstance(node, ast.Assign):
			targets = node.targets
		elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
			targets = [node.target]
		for t in targets:
			base = t
			while isinstance(base, ast.Subscript):
				base = base.value
			if isinstance(base, ast.Attribute) and isinstance(base.value, ast.Name) and base.value.id != "self":
				out.append((base.value.id, base.attr, node.lineno))
	return out


print("SkillVerify pre-submission AST audit")
print("=" * 70)

trees = {p: ast.parse(p.read_text(encoding="utf8")) for p in SOURCES}
for p in ARTIFACTS:
	if p.exists():
		trees[p] = ast.parse(p.read_text(encoding="utf8"))

# ── 1. WRITE-THEN-RAISE ───────────────────────────────────────────────────
print("\n1. no state write is followed by a raise  (PackageGuard/Joaquin)")
hits = 0
for path, tree in trees.items():
	for cls in classes(tree):
		for fn in methods(cls):
			for line in raises_after_write(fn):
				finding("write-then-raise", path, line, f"{cls.name}.{fn.name} writes state then raises")
				hits += 1
(ok if not hits else bad)("every mutator refuses first and writes last", f"{len(trees)} files")

# ── 2. FROZEN-STATE MUTATION ──────────────────────────────────────────────
print("\n2. no write is reachable after a terminal status  (PackageGuard/Joaquin)")
hits = 0
EXEMPT = {"_apply", "_summary", "__init__", "verify_skill", "post_bounty"}
for path in SOURCES:
	tree = trees[path]
	for cls in classes(tree):
		for fn in methods(cls):
			if fn.name in EXEMPT:
				continue
			writes = [w for w in record_writes(fn) if w[0] in ("record", "bounty")]
			if writes and not calls_named(fn, "_mutable"):
				finding("frozen-state", path, writes[0][2], f"{cls.name}.{fn.name} writes a record without the _mutable gate")
				hits += 1
(ok if not hits else bad)("every record mutator holds the _mutable gate")

# The two exempt creators must only ever reach a FRESH id.
for path in SOURCES:
	tree = trees[path]
	for cls in classes(tree):
		for fn in methods(cls):
			if fn.name not in ("verify_skill", "post_bounty"):
				continue
			src = ast.unparse(fn)
			if "next_id" not in src or "get_or_insert_default" not in src:
				finding("frozen-state", path, fn.lineno, f"{fn.name} does not allocate a fresh id before writing")
(ok if not [f for f in findings if "fresh id" in f] else bad)("the two record creators allocate a fresh id first")

# ── 3. UNSNAPSHOTTED TERMS ────────────────────────────────────────────────
print("\n3. per-record terms are frozen on the record  (PredictStake/Pavel)")
# A term the owner can move must be read from the RECORD, never from the live
# config, anywhere a record is being judged.
SNAPSHOT_FIELDS = ("resolve_window", "fee")
hits = 0
tree = trees[SOURCES[0]]
for cls in classes(tree):
	for fn in methods(cls):
		if fn.name not in ("settle_stalled", "resolve_pending"):
			continue
		for node in ast.walk(fn):
			# self.resolve_window inside a settle decision would read the LIVE
			# default and let an owner keep an old record in flight.
			if isinstance(node, ast.Attribute) and node.attr in SNAPSHOT_FIELDS:
				if isinstance(node.value, ast.Name) and node.value.id == "self":
					finding("unsnapshotted-term", SOURCES[0], node.lineno,
						f"{fn.name} reads the live self.{node.attr} instead of the record's")
					hits += 1
(ok if not hits else bad)("settle_stalled and resolve_pending read the record's own frozen terms")

# And the record must actually carry them.
verification = None
for node in ast.walk(trees[SOURCES[0]]):
	if isinstance(node, ast.ClassDef) and node.name == "Verification":
		verification = {n.target.id for n in node.body if isinstance(n, ast.AnnAssign)}
missing = [f for f in ("resolve_window", "fee_snapshot", "bytes_basis") if f not in (verification or set())]
if missing:
	finding("unsnapshotted-term", SOURCES[0], 0, f"Verification lacks {missing}")
(ok if not missing else bad)("Verification carries resolve_window, fee_snapshot and bytes_basis")

# ── 4. PAYABLE REVERT ─────────────────────────────────────────────────────
print("\n4. no payable method can raise  (ClaimStake/Pavel)")
hits = 0
payables = []
for path in SOURCES:
	tree = trees[path]
	for cls in classes(tree):
		for fn in methods(cls):
			if not any("payable" in d for d in decorators(fn)):
				continue
			payables.append(f"{path.name}:{cls.name}.{fn.name}")
			for node in ast.walk(fn):
				if isinstance(node, ast.Raise):
					finding("payable-revert", path, node.lineno, f"{fn.name} raises on a payable path")
					hits += 1
			# It must also refund. A payable method with no _reject call has no
			# way to return value it turns down.
			if not calls_named(fn, "_reject"):
				finding("payable-revert", path, fn.lineno, f"{fn.name} is payable but never calls _reject")
				hits += 1
(ok if not hits else bad)("payable methods refund and return", ", ".join(payables))

# Everything a payable method calls must also not raise.
print("     (and every helper a payable path reaches)")
RAISING = set()
for path in SOURCES:
	tree = trees[path]
	for node in ast.walk(tree):
		if isinstance(node, ast.FunctionDef) and any(isinstance(n, ast.Raise) for n in ast.walk(node)):
			RAISING.add(node.name)
hits = 0
for path in SOURCES:
	tree = trees[path]
	for cls in classes(tree):
		for fn in methods(cls):
			if not any("payable" in d for d in decorators(fn)):
				continue
			for node in ast.walk(fn):
				if isinstance(node, ast.Call):
					f = node.func
					name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
					if name in RAISING and name not in ("UserError",):
						finding("payable-revert", path, node.lineno, f"{fn.name} calls {name}, which can raise")
						hits += 1
(ok if not hits else bad)("no payable path reaches a raising helper")

# ── 5. OWNER REACH ────────────────────────────────────────────────────────
print("\n5. the owner cannot reach a user record or a user's funds")
hits = 0
tree = trees[SOURCES[0]]
for cls in classes(tree):
	for fn in methods(cls):
		if not calls_named(fn, "_only_owner"):
			continue
		if record_writes(fn):
			finding("owner-reach", SOURCES[0], fn.lineno, f"{fn.name} writes a verification record")
			hits += 1
		for node in ast.walk(fn):
			if isinstance(node, ast.Attribute) and node.attr in ("verifications", "latest_resolved", "inflight", "by_pair"):
				finding("owner-reach", SOURCES[0], node.lineno, f"{fn.name} reaches self.{node.attr}")
				hits += 1
(ok if not hits else bad)("no owner method touches a verification")

# The consumer's owner must not be able to move a poster's money.
ctree = trees[SOURCES[1]]
hits = 0
for cls in classes(ctree):
	for fn in methods(cls):
		if fn.name != "withdraw_bounty":
			continue
		src = ast.unparse(fn)
		if "bounty.poster" not in src:
			finding("owner-reach", SOURCES[1], fn.lineno, "withdraw_bounty does not check the poster")
			hits += 1
	# There must be no owner-gated method in the consumer at all.
	for fn in methods(cls):
		if calls_named(fn, "_only_owner"):
			finding("owner-reach", SOURCES[1], fn.lineno, f"{fn.name} is owner-gated in a contract holding user funds")
			hits += 1
(ok if not hits else bad)("only the poster can withdraw a bounty, and the consumer has no owner powers")

# ── 6. STORED-FIELD PROVENANCE ────────────────────────────────────────────
print("\n6. every stored field is recomputed from the agreed evidence")
apply_fn = None
for cls in classes(trees[SOURCES[0]]):
	for fn in methods(cls):
		if fn.name == "_apply":
			apply_fn = fn
src = ast.unparse(apply_fn) if apply_fn else ""
required = [
	("level is recomputed from the counts", "_level_for(repo_count, total_bytes)"),
	("content_hash is derived from the stored fields", "_content_hash("),
	("counts are clamped before they meet a sized integer", "_clamp("),
]
for label, needle in required:
	(ok if needle in src else bad)(label)
	if needle not in src:
		finding("provenance", SOURCES[0], apply_fn.lineno if apply_fn else 0, label + " — missing " + needle)
# The hash must be computed AFTER the fields it covers are assigned.
if apply_fn:
	lines = src.splitlines()
	hash_line = next((i for i, l in enumerate(lines) if "_content_hash(" in l), -1)
	level_line = next((i for i, l in enumerate(lines) if "record.level = " in l), -1)
	good = hash_line > level_line >= 0
	(ok if good else bad)("the hash is computed after the fields it covers")
	if not good:
		finding("provenance", SOURCES[0], apply_fn.lineno, "content_hash computed before its inputs were stored")

# ── 7. str.replace ────────────────────────────────────────────────────────
print("\n7. no str.replace()  (rejected by the runner)")
hits = 0
for path, tree in trees.items():
	for node in ast.walk(tree):
		if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "replace":
			finding("str-replace", path, node.lineno, "calls .replace()")
			hits += 1
(ok if not hits else bad)("no .replace() anywhere, source or artifact")

# ── 8. SELF IN A NONDET CLOSURE ───────────────────────────────────────────
print("\n8. no nondet closure captures self  (pickles storage, kills the leader)")
hits = 0
for path, tree in trees.items():
	for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
		uses_nondet = any(
			isinstance(n, ast.Call) and (
				(isinstance(n.func, ast.Attribute) and n.func.attr.startswith("run_nondet"))
				or (isinstance(n.func, ast.Name) and n.func.id.startswith("run_nondet")))
			for n in ast.walk(fn))
		if not uses_nondet:
			continue
		for inner in fn.body:
			if isinstance(inner, ast.FunctionDef):
				for sub in ast.walk(inner):
					if isinstance(sub, ast.Name) and sub.id == "self":
						finding("nondet-self", path, sub.lineno, f"{fn.name}.{inner.name} references self")
						hits += 1
(ok if not hits else bad)("every nondet closure is built from copied scalars")

# ── 9. ARTIFACT SIZE ──────────────────────────────────────────────────────
print("\n9. artifact size  (the ceiling that decides whether this deploys)")
for path in ARTIFACTS:
	if not path.exists():
		bad(f"{path.name} missing — run tools/build.sh")
		findings.append(f"artifact-size: {path.name} not built")
		continue
	size = len(path.read_bytes())
	within = size < ARTIFACT_BUDGET
	(ok if within else bad)(f"{path.name} is {size:,} bytes", f"budget {ARTIFACT_BUDGET:,}")
	if not within:
		findings.append(f"artifact-size: {path.name} is {size} bytes, over the {ARTIFACT_BUDGET} budget")

# ── result ────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
if findings:
	print(f"{len(findings)} FINDING(S):")
	for f in findings:
		print(f"  - {f}")
else:
	print(f"{checks} checks, no findings.")
print("=" * 70)
sys.exit(len(findings))
