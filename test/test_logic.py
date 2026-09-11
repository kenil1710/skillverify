#!/usr/bin/env python3
"""Offline tests for SkillVerify. No chain, no network, no model, no genlayer
install. stdlib only:

    python3 test/test_logic.py

Seven things are under test, not one.

1. **The pure scoring engine** in `contracts/SkillVerify.py` — normalisation,
   validation, percent-encoding, URL construction, the ladder, and `_score`.
   This is the half every validator computes after the bytes come back, and it
   is all deterministic integer Python. If two validators disagree here, no
   verification ever settles.

2. **Extraction against REAL bodies.** `test/fixtures.json` holds verbatim
   responses from the exact search URLs the validators fetch, captured
   2026-09-07 and cross-checked against what the on-chain probe measured for
   the same queries (docs/PROBE.md). Every extraction assertion is made against
   the document GitHub actually sends, not against a hand-written idea of it.

3. **THE AST SCANS.** Three of them, and they are the reason this file exists
   in the shape it does:
     - no state write may be followed by a `raise` on any path;
     - no state write may be reachable after a record reaches a terminal
       status, and every mutator must pass through `_mutable`;
     - no closure handed to `run_nondet` may reference `self`.
   Each of these is a bug class a previous project was rejected for. They are
   checked by parsing the file rather than by remembering, because remembering
   is what failed the first time.

4. **A static undefined-name check** over the WHOLE file, class bodies
   included. A NameError inside a `@gl.public.view` only fires when that view is
   called on chain. A parser catches it in a millisecond; a deploy catches it in
   ten minutes.

5. **The stateful contract**, driven through a storage stub rich enough to run
   verify → resolve → settle end to end with consensus wired up. This is where
   the money properties are proved: that a rejected payable call REFUNDS rather
   than confiscating, and that a terminal record is unreachable from every
   method including the owner's.

6. **The consumer across a real call boundary.** `SkillConsumer` is wired to an
   actual `SkillVerify` instance, not a fake — because the bug being guarded
   against is precisely that the real oracle might raise where a fake would
   politely return whatever the test author expected.

7. **The artifact.** The same battery re-run through `build/SkillVerify.min.py`
   when it exists. The minified file is what gets deployed, so "the source is
   correct" is only half a claim.
"""

import ast
import builtins
import json
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "contracts" / "SkillVerify.py"
CONSUMER = ROOT / "contracts" / "SkillConsumer.py"
ARTIFACT = ROOT / "build" / "SkillVerify.min.py"
CONSUMER_ARTIFACT = ROOT / "build" / "SkillConsumer.min.py"
FIXTURES = ROOT / "test" / "fixtures.json"

# Bradbury refused a 59,278-byte artifact with `BlockPubdataLimitReached` in an
# earlier project. 48,000 is that refusal with a safety margin under it, and it
# is asserted before anything else because it is the constraint that decides
# whether this project can ship at all.
ARTIFACT_BUDGET = 48_000
SOURCE_BUDGET = 140 * 1024

GEN = 10 ** 18


# ---------------------------------------------------------------------------
# runtime stub — carried forward from the proven PredictStake/CropShield
# harness. The TreeMap missing-key semantics are load-bearing: on chain a map
# with a SCALAR value type answers a missing key with that type's ZERO, not with
# None, so a presence check written as `is not None` matches everything. A stub
# that returned None for every missing key could never reproduce that bug, and
# SkillVerify has six such maps.
# ---------------------------------------------------------------------------

_UNSET = object()


class _UserError(Exception):
	def __init__(self, message: str = ""):
		super().__init__(message)
		self.message = message


def _offline(*_a, **_k):
	raise AssertionError("offline tests must not touch the network or a model")


class _Return:
	def __init__(self, calldata):
		self.calldata = calldata


class _Rollback:
	def __init__(self, message=""):
		self.message = message


class _Addr:
	def __init__(self, value=""):
		self._v = str(value).lower() if str(value).startswith("0x") else str(value)

	def __str__(self):
		return self._v

	def __repr__(self):
		return "Address(" + self._v + ")"

	def __eq__(self, other):
		return str(self) == str(other)

	def __hash__(self):
		return hash(self._v)


class _TreeMap(dict):
	"""Models the runtime's TreeMap INCLUDING what it returns for a missing key.

	On chain a `TreeMap[str, u32]` answers a missing key with the value type's
	ZERO. `if m.get(k) is not None` is therefore always true. CropShield shipped
	exactly that bug and every farmer's first policy was refused as a duplicate.
	Struct-valued maps DO answer None, which is why `if found is None` is the
	correct idiom for those and only those.
	"""

	_value_type = None

	@classmethod
	def __class_getitem__(cls, item):
		vt = item[1] if isinstance(item, tuple) and len(item) > 1 else None
		return type("_TreeMapOf", (cls,), {"_value_type": vt})

	def _k(self, key):
		return str(key) if isinstance(key, _Addr) else key

	def _missing(self):
		vt = type(self)._value_type
		if vt is None:
			return None
		name = getattr(vt, "__name__", str(vt))
		if name.startswith("_TreeMap") or name.startswith("_DynArray"):
			return _zero_for(vt)
		if vt is int or vt is str or vt is bool:
			return _zero_for(vt)
		if hasattr(vt, "__annotations__") and getattr(vt, "__annotations__"):
			return None
		return _zero_for(vt)

	def get(self, key, default=_UNSET):
		k = self._k(key)
		if k in self:
			return dict.__getitem__(self, k)
		if default is not _UNSET:
			return default
		return self._missing()

	def __setitem__(self, key, value):
		dict.__setitem__(self, self._k(key), value)

	def __getitem__(self, key):
		return dict.__getitem__(self, self._k(key))

	def get_or_insert_default(self, key):
		k = self._k(key)
		if k not in self:
			dict.__setitem__(self, k, self._factory())
		return dict.__getitem__(self, k)


class _DynArray(list):
	_elem_type = None

	@classmethod
	def __class_getitem__(cls, item):
		return type("_DynArrayOf", (cls,), {"_elem_type": item})

	def append_new_get(self):
		elem = type(self)._elem_type
		value = _make_struct(elem) if elem is not None and hasattr(elem, "__annotations__") else _zero_for(elem)
		list.append(self, value)
		return value


def _zero_for(annotation):
	name = getattr(annotation, "__name__", str(annotation))
	if annotation is bool or name == "bool":
		return False
	if annotation is str or name == "str":
		return ""
	if name == "_Addr" or name == "Address":
		return _Addr("0x" + "0" * 40)
	if name == "_TreeMap" or name == "TreeMap" or name.startswith("_TreeMapOf"):
		return annotation() if isinstance(annotation, type) else _TreeMap()
	if name == "_DynArray" or name == "DynArray" or name.startswith("_DynArrayOf"):
		return annotation() if isinstance(annotation, type) else _DynArray()
	if name.startswith("u") or name.startswith("i"):
		return 0
	if hasattr(annotation, "__annotations__"):
		return _make_struct(annotation)
	return 0


def _make_struct(cls):
	obj = cls.__new__(cls)
	for field, ann in getattr(cls, "__annotations__", {}).items():
		setattr(obj, field, _zero_for(ann))
	return obj


class _Contract:
	balance = 0

	def __getattr__(self, name):
		anns = {}
		for klass in reversed(type(self).__mro__):
			anns.update(getattr(klass, "__annotations__", {}))
		if name in anns:
			value = _zero_for(anns[name])
			if isinstance(value, _TreeMap):
				value._factory = _factory_for(type(self), name)
			object.__setattr__(self, name, value)
			return value
		raise AttributeError(name)


_STRUCT_HINTS = {}


def _factory_for(contract_cls, field):
	target = _STRUCT_HINTS.get((contract_cls.__name__, field))
	if target is None:
		return lambda: _DynArray()
	return lambda: _make_struct(target)


TRANSFERS = []


def _contract_interface(cls):
	class _Handle:
		def __init__(self, to):
			self.to = to

		def emit_transfer(self, value=0):
			TRANSFERS.append((str(self.to), int(value)))

	return _Handle


ORACLE = {"impl": None, "raise_on": None}


class _OracleHandle:
	"""What gl.get_contract_at returns. `.view()` hands back the REAL contract
	instance the test wired in, so a consumer test exercises the actual
	SkillVerify across the call boundary. `raise_on` lets a test make the oracle
	raise on a named method, which is the failure the consumer's wrapping
	exists to survive."""

	def __init__(self, address):
		self.address = address

	def _target(self):
		impl = ORACLE["impl"]
		if impl is None:
			raise _UserError("no oracle wired")
		return _Guard(impl)

	def view(self):
		return self._target()

	def write(self):
		return self._target()


class _Guard:
	def __init__(self, impl):
		self._impl = impl

	def __getattr__(self, name):
		if ORACLE.get("raise_on") == name:
			def _boom(*_a, **_k):
				raise _UserError("oracle exploded in " + name)
			return _boom
		return getattr(self._impl, name)


MESSAGE = types.SimpleNamespace(sender_address=_Addr("0x" + "a" * 40), value=0)
MESSAGE_RAW = {"datetime": "2026-09-07T12:00:00Z"}

# What the stubbed "network" hands the leader. Each entry is (status, body).
FETCH_QUEUE = []
FETCH_LOG = []
LAST_CONSENSUS = {}
# When set, the validator's own re-run returns this instead, so a genuine
# leader/validator disagreement can be staged.
VALIDATOR_QUEUE = []
# A MALICIOUS LEADER. Each entry is a callable applied to the leader's result
# dict AFTER it is computed and BEFORE the validator or the contract ever sees
# it — which is exactly the power a real leader has: it does the work honestly
# or dishonestly and broadcasts whatever payload it likes. Nothing else in the
# harness can stage the forgery this project was rejected for, because that
# forgery lives in the gap between what a leader computed and what it reported.
LEADER_FORGE = []


class _Response:
	def __init__(self, status, body):
		self.status = status
		self.body = body


def _web_request(url, method="GET", **_k):
	FETCH_LOG.append(url)
	if not FETCH_QUEUE:
		raise AssertionError("fetch with an empty FETCH_QUEUE: " + url)
	status, body = FETCH_QUEUE.pop(0)
	if isinstance(status, Exception):
		raise status
	return _Response(status, body)


def _run_nondet(leader_fn, validator_fn):
	"""Runs the real consensus shape offline: the leader produces a result, a
	validator is handed it as gl.vm.Return and must agree, and disagreement is
	surfaced as UNDETERMINED rather than silently ignored — because on chain it
	applies NOTHING, and a stub that quietly returned the leader's answer would
	let every test pass while consensus was broken."""
	result = leader_fn()
	if LEADER_FORGE:
		# The leader tampers with its own payload before broadcasting it. The
		# validator is handed the FORGED document and the contract applies the
		# FORGED document, which is what happens on chain.
		result = LEADER_FORGE.pop(0)(result)
	# The validator RE-RUNS the leader function, so its own response has to be
	# in the queue before it is called. A test stages a genuine disagreement by
	# putting a different body in VALIDATOR_QUEUE.
	if VALIDATOR_QUEUE:
		FETCH_QUEUE.extend(VALIDATOR_QUEUE.pop(0))
	agreed = validator_fn(_Return(result))
	LAST_CONSENSUS["agreed"] = bool(agreed)
	LAST_CONSENSUS["result"] = result
	if not agreed:
		raise AssertionError("UNDETERMINED: validator did not agree with leader")
	return result


def _install_stub():
	if "genlayer" in sys.modules:
		return
	mod = types.ModuleType("genlayer")
	vm = types.SimpleNamespace(UserError=_UserError, Return=_Return,
		Result=object, Rollback=_Rollback, run_nondet=_run_nondet,
		run_nondet_unsafe=_run_nondet)
	web = types.SimpleNamespace(request=_web_request, render=_offline, get=_web_request)
	nondet = types.SimpleNamespace(web=web, exec_prompt=_offline)
	public = types.SimpleNamespace()
	public.view = lambda fn: fn
	write = lambda fn: fn
	write.payable = lambda fn: fn
	public.write = write
	evm = types.SimpleNamespace(contract_interface=_contract_interface)
	mod.gl = types.SimpleNamespace(vm=vm, nondet=nondet, public=public,
		evm=evm, message=MESSAGE, message_raw=MESSAGE_RAW, Contract=_Contract,
		contract_interface=lambda c: _OracleHandle,
		get_contract_at=lambda a: _OracleHandle(a))
	mod.Address = _Addr
	mod.TreeMap = _TreeMap
	mod.DynArray = _DynArray
	mod.allow_storage = lambda cls: cls
	for name in ("u8", "u16", "u32", "u64", "u128", "u256", "i8", "i16",
			"i32", "i64", "bigint"):
		mod.__dict__[name] = int
	sys.modules["genlayer"] = mod


def load_pure(path: Path, name: str) -> types.ModuleType:
	"""Exec only the pure region — every top-level statement before the first
	class definition. That region never touches storage."""
	tree = ast.parse(path.read_text(encoding="utf8"))
	cut = len(tree.body)
	for i, node in enumerate(tree.body):
		if isinstance(node, ast.ClassDef):
			cut = i
			break
	tree.body = tree.body[:cut]
	module = types.ModuleType(name)
	module.__file__ = str(path)
	exec(compile(tree, str(path), "exec"), module.__dict__)
	return module


def load_full(path: Path, name: str) -> types.ModuleType:
	module = types.ModuleType(name)
	module.__file__ = str(path)
	exec(compile(path.read_text(encoding="utf8"), str(path), "exec"), module.__dict__)
	return module


# ---------------------------------------------------------------------------
# static undefined-name check
# ---------------------------------------------------------------------------

def _own_nodes(scope):
	out = []

	def rec(node):
		for sub in ast.iter_child_nodes(node):
			if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
				continue
			out.append(sub)
			rec(sub)
	rec(scope)
	return out


def _child_scopes(scope):
	out = []

	def rec(node):
		for sub in ast.iter_child_nodes(node):
			if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
				out.append(sub)
			else:
				rec(sub)
	rec(scope)
	return out


def _bound_names(scope) -> set:
	out = set()
	args = getattr(scope, "args", None)
	if args is not None:
		for group in (args.posonlyargs, args.args, args.kwonlyargs):
			for a in group:
				out.add(a.arg)
		if args.vararg:
			out.add(args.vararg.arg)
		if args.kwarg:
			out.add(args.kwarg.arg)
	for sub in _own_nodes(scope):
		if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
			out.add(sub.id)
		elif isinstance(sub, ast.ExceptHandler) and sub.name:
			out.add(sub.name)
		elif isinstance(sub, (ast.Global, ast.Nonlocal)):
			out.update(sub.names)
		elif isinstance(sub, (ast.Import, ast.ImportFrom)):
			for al in sub.names:
				out.add((al.asname or al.name).split(".")[0])
		elif isinstance(sub, ast.comprehension):
			for nm in ast.walk(sub.target):
				if isinstance(nm, ast.Name):
					out.add(nm.id)
	for sub in _child_scopes(scope):
		if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
			out.add(sub.name)
	for sub in _own_nodes(scope):
		if isinstance(sub, ast.ClassDef):
			out.add(sub.name)
	return out


def undefined_names(path: Path) -> list:
	tree = ast.parse(path.read_text(encoding="utf8"))
	module_names = _bound_names(tree) | {
		"gl", "u8", "u16", "u32", "u64", "u128", "u256", "i8", "i16", "i32",
		"i64", "Address", "TreeMap", "DynArray", "allow_storage", "bigint",
		"Array", "self"}
	builtin_names = set(dir(builtins))
	problems = []

	def visit(scope, enclosing, label):
		scope_names = enclosing | _bound_names(scope)
		for sub in _own_nodes(scope):
			if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
				if sub.id not in scope_names and sub.id not in builtin_names:
					problems.append((label, sub.id, sub.lineno))
		for child in _child_scopes(scope):
			visit(child, scope_names, label + "." + getattr(child, "name", "<lambda>"))

	for child in _child_scopes(tree):
		visit(child, module_names, getattr(child, "name", "<lambda>"))
	for node in _own_nodes(tree):
		if isinstance(node, ast.ClassDef):
			for child in _child_scopes(node):
				visit(child, module_names | _bound_names(node),
					node.name + "." + getattr(child, "name", "<lambda>"))
	return problems


# ---------------------------------------------------------------------------
# The three bug-class scanners.
# ---------------------------------------------------------------------------

def _is_state_write(node) -> bool:
	"""`self.x = ...`, `self.x[k] = ...`, or `record.field = ...`.

	Deliberately broad: it counts writes to any attribute of any local as well
	as to self, because a Verification handle pulled out of storage IS storage
	and `record.status = ...` is a state write by any useful definition."""
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


def _raises_after_write(fn) -> list:
	"""Every state write with a `raise` reachable AFTER it in the same
	statement list, or in any block that follows it.

	THE PACKAGEGUARD REJECTION, encoded. A counter incremented and then rolled
	back by a revert is at best dead work and at worst — when the revert is
	conditional on something the counter itself influences — a state machine
	that disagrees with its own history. The fix in this project is structural:
	every mutating method does all of its refusing first and all of its writing
	last, so this scanner returns nothing at all.
	"""
	problems = []

	def scan(body, seen_write):
		for stmt in body:
			if _is_state_write(stmt):
				seen_write = True
				continue
			if isinstance(stmt, ast.Raise) and seen_write:
				problems.append(stmt.lineno)
				continue
			for field in ("body", "orelse", "finalbody"):
				inner = getattr(stmt, field, None)
				if isinstance(inner, list):
					scan(inner, seen_write)
			for handler in getattr(stmt, "handlers", []) or []:
				scan(handler.body, seen_write)
			# A write nested inside an if/for/while still counts for the
			# statements that follow the compound statement.
			if any(_writes_anywhere(getattr(stmt, f, []) or []) for f in ("body", "orelse", "finalbody")):
				seen_write = True

	def _writes_anywhere(body):
		for stmt in body:
			if _is_state_write(stmt):
				return True
			for field in ("body", "orelse", "finalbody"):
				inner = getattr(stmt, field, None)
				if isinstance(inner, list) and _writes_anywhere(inner):
					return True
		return False

	scan(fn.body, False)
	return problems


def _contract_class(tree, name):
	for node in tree.body:
		if isinstance(node, ast.ClassDef) and node.name == name:
			return node
	raise AssertionError("no class " + name)


def _methods(cls):
	return [n for n in cls.body if isinstance(n, ast.FunctionDef)]


def _decorator_names(fn):
	out = []
	for dec in fn.decorator_list:
		out.append(ast.unparse(dec))
	return out


def _calls_named(fn, name) -> bool:
	for node in ast.walk(fn):
		if isinstance(node, ast.Call):
			f = node.func
			if isinstance(f, ast.Attribute) and f.attr == name:
				return True
			if isinstance(f, ast.Name) and f.id == name:
				return True
	return False


def _writes_record_fields(fn) -> list:
	"""Writes to a field of a local that is not `self` — i.e. to a storage
	struct handle pulled out of a TreeMap."""
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


def _nondet_closures_referencing_self(tree) -> list:
	"""Any function passed to run_nondet whose body mentions `self`.

	Capturing `self` in a nondet closure PICKLES CONTRACT STORAGE into the
	nondeterministic block and kills the leader at `run_time 0s` with no error
	worth reading. Every helper in this project is module level and every value
	a closure needs is copied through str()/int() first, so this returns
	nothing."""
	problems = []
	for node in ast.walk(tree):
		if not isinstance(node, ast.Call):
			continue
		f = node.func
		fname = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
		if fname not in ("run_nondet", "run_nondet_unsafe"):
			continue
		# Find the enclosing function and check its nested defs.
		for parent in ast.walk(tree):
			if not isinstance(parent, ast.FunctionDef):
				continue
			if node not in list(ast.walk(parent)):
				continue
			for inner in parent.body:
				if isinstance(inner, ast.FunctionDef):
					for sub in ast.walk(inner):
						if isinstance(sub, ast.Name) and sub.id == "self":
							problems.append((parent.name, inner.name, sub.lineno))
	return problems


# ---------------------------------------------------------------------------
# fixtures — verbatim bodies, captured 2026-09-07
# ---------------------------------------------------------------------------

_RAW = json.loads(FIXTURES.read_text(encoding="utf8"))
FIX = _RAW["fixtures"]


def fixture_body(name) -> str:
	entry = FIX[name]
	body = entry["body"]
	return body if isinstance(body, str) else json.dumps(body)


def fixture_status(name) -> int:
	return int(FIX[name]["status"])


def fixture_doc(name):
	entry = FIX[name]
	return entry["body"] if not isinstance(entry["body"], str) else json.loads(entry["body"])


_install_stub()
SV = load_pure(SOURCE, "sv_pure")
SC = load_pure(CONSUMER, "sc_pure")
SV_TREE = ast.parse(SOURCE.read_text(encoding="utf8"))
SC_TREE = ast.parse(CONSUMER.read_text(encoding="utf8"))

_FULL = load_full(SOURCE, "sv_full")
_CFULL = load_full(CONSUMER, "sc_full")
SkillVerify = _FULL.SkillVerify
SkillConsumer = _CFULL.SkillConsumer
Verification = _FULL.Verification
Bounty = _CFULL.Bounty
_STRUCT_HINTS[("SkillVerify", "verifications")] = Verification
_STRUCT_HINTS[("SkillConsumer", "bounties")] = Bounty


# ---------------------------------------------------------------------------
# helpers for the stateful tests
# ---------------------------------------------------------------------------

OWNER = _Addr("0x" + "a" * 40)
ALICE = _Addr("0x" + "b" * 40)
BOB = _Addr("0x" + "c" * 40)
CAROL = _Addr("0x" + "d" * 40)

RATE_LIMIT_BODY = json.dumps({
	"message": "API rate limit exceeded for 44.198.152.104. (But here's the good news: "
	           "Authenticated requests get a higher rate limit.)",
	"documentation_url": "https://docs.github.com/rest/overview/rate-limits-for-the-rest-api",
})


def as_sender(addr, value=0):
	MESSAGE.sender_address = addr
	MESSAGE.value = int(value)


def set_clock(iso):
	MESSAGE_RAW["datetime"] = iso


def queue_ok(name):
	"""Queue the leader's fetch AND the validator's re-run with the same body,
	which is what a committing round looks like."""
	body = fixture_body(name)
	status = fixture_status(name)
	FETCH_QUEUE.append((status, body))
	VALIDATOR_QUEUE.append([(status, body)])


def queue_raw(status, body, validator=None):
	FETCH_QUEUE.append((status, body))
	VALIDATOR_QUEUE.append([validator if validator is not None else (status, body)])


def reset_world():
	FETCH_QUEUE.clear()
	VALIDATOR_QUEUE.clear()
	LEADER_FORGE.clear()
	FETCH_LOG.clear()
	TRANSFERS.clear()
	LAST_CONSENSUS.clear()
	ORACLE["impl"] = None
	ORACLE["raise_on"] = None
	as_sender(OWNER, 0)
	set_clock("2026-09-07T12:00:00Z")


def new_oracle(fee=0):
	reset_world()
	as_sender(OWNER, 0)
	c = SkillVerify(fee)
	return c


def new_consumer(oracle):
	c = SkillConsumer(str(_Addr("0x" + "e" * 40)))
	ORACLE["impl"] = oracle
	return c


def jload(text):
	return json.loads(text)


NOW = SV._epoch_from_iso("2026-09-07T12:00:00Z")


def clock_at(offset_seconds):
	"""Move the stub clock `offset_seconds` past the 2026-09-07T12:00:00Z
	anchor, by asking the contract's own calendar code so the test and the
	contract can never disagree about what a timestamp means."""
	target = NOW + int(offset_seconds)
	days, rem = divmod(target, 86400)
	h, rem = divmod(rem, 3600)
	mi, s = divmod(rem, 60)
	# Invert _days_from_civil by searching the small neighbourhood — exact and
	# obviously correct, and it runs once per call.
	y = 1970
	while SV._days_from_civil(y + 1, 1, 1) <= days:
		y += 1
	m = 1
	while m < 12 and SV._days_from_civil(y, m + 1, 1) <= days:
		m += 1
	d = days - SV._days_from_civil(y, m, 1) + 1
	set_clock("%04d-%02d-%02dT%02d:%02d:%02dZ" % (y, m, d, h, mi, s))
	return target


# ═══════════════════════════════════════════════════════════════════════════
# 1. STATIC GATES — the constraints that decide whether this ships at all.
# ═══════════════════════════════════════════════════════════════════════════

class TestStaticGates(unittest.TestCase):

	def test_runner_is_pinned_on_line_one(self):
		for path in (SOURCE, CONSUMER):
			first = path.read_text(encoding="utf8").splitlines()[0]
			self.assertTrue(first.startswith('# { "Depends": "py-genlayer:'), path.name)
			self.assertNotIn("py-genlayer:test", first)
			self.assertNotIn("py-genlayer:latest", first)
			# A 52-character content hash, not an alias. Every GenLayer network
			# rejects an unpinned runner and reports only `invalid_contract`.
			self.assertRegex(first, r'py-genlayer:[a-z0-9]{40,}"')

	def test_nothing_sits_between_line_one_and_the_import(self):
		# GenVM parses the whole CONTIGUOUS leading `#` block as the runner
		# JSON. A comment above or immediately after line 1 makes the contract
		# undeployable and the only error reported is `invalid_contract`.
		for path in (SOURCE, CONSUMER):
			lines = path.read_text(encoding="utf8").splitlines()
			self.assertTrue(lines[1].startswith("from genlayer import"), path.name)

	def test_source_within_budget(self):
		for path in (SOURCE, CONSUMER):
			self.assertLess(len(path.read_bytes()), SOURCE_BUDGET, path.name)

	def test_no_str_replace_anywhere(self):
		# The runner rejects str.replace(). Slice around find() instead.
		for tree, name in ((SV_TREE, "SkillVerify"), (SC_TREE, "SkillConsumer")):
			for node in ast.walk(tree):
				if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
					self.assertNotEqual(node.func.attr, "replace",
						name + " calls .replace() at line " + str(node.lineno))

	def test_no_undefined_names_in_oracle(self):
		self.assertEqual(undefined_names(SOURCE), [])

	def test_no_undefined_names_in_consumer(self):
		self.assertEqual(undefined_names(CONSUMER), [])

	def test_no_bare_exception_raised(self):
		# `raise Exception(...)` becomes an unrecoverable VMError. Every raise
		# must be a gl.vm.UserError.
		for tree, name in ((SV_TREE, "SkillVerify"), (SC_TREE, "SkillConsumer")):
			for node in ast.walk(tree):
				if isinstance(node, ast.Raise) and node.exc is not None:
					rendered = ast.unparse(node.exc)
					self.assertTrue(rendered.startswith("gl.vm.UserError"),
						name + " line " + str(node.lineno) + ": " + rendered)

	def test_no_float_literals_in_scoring(self):
		# Nothing that decides a level may be a float: two validators formatting
		# a float differently is a disagreement over nothing.
		for node in ast.walk(SV_TREE):
			if isinstance(node, ast.Constant) and isinstance(node.value, float):
				self.fail("float literal at line " + str(node.lineno))

	def test_no_true_division_in_oracle(self):
		for node in ast.walk(SV_TREE):
			if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
				self.fail("true division at line " + str(node.lineno) + " — use //")


class TestNoWriteBeforeRaise(unittest.TestCase):
	"""THE PACKAGEGUARD REJECTION, as a test.

	No state write anywhere in either contract may have a `raise` reachable
	after it. The project satisfies this structurally: every mutating method
	refuses first and writes last, with an explicit COMMIT comment marking the
	line past which nothing can refuse."""

	def test_oracle_has_no_write_then_raise(self):
		cls = _contract_class(SV_TREE, "SkillVerify")
		offenders = []
		for fn in _methods(cls):
			for line in _raises_after_write(fn):
				offenders.append((fn.name, line))
		self.assertEqual(offenders, [])

	def test_consumer_has_no_write_then_raise(self):
		cls = _contract_class(SC_TREE, "SkillConsumer")
		offenders = []
		for fn in _methods(cls):
			for line in _raises_after_write(fn):
				offenders.append((fn.name, line))
		self.assertEqual(offenders, [])

	def test_the_scanner_actually_catches_the_bug(self):
		# A scanner that cannot fail proves nothing. This is the shape it must
		# reject, and if this assertion ever passes trivially the two tests
		# above are decorative.
		bad = ast.parse(
			"def f(self):\n"
			"    self.counter = self.counter + 1\n"
			"    if x:\n"
			"        raise gl.vm.UserError('no')\n"
		).body[0]
		self.assertTrue(_raises_after_write(bad))

	def test_scanner_accepts_the_correct_shape(self):
		good = ast.parse(
			"def f(self):\n"
			"    if x:\n"
			"        raise gl.vm.UserError('no')\n"
			"    self.counter = self.counter + 1\n"
		).body[0]
		self.assertEqual(_raises_after_write(good), [])


class TestTerminalStatesAreFrozen(unittest.TestCase):
	"""THE OTHER PACKAGEGUARD REJECTION: no state mutation after a freeze.

	Every method that writes to a Verification (or a Bounty) field must first
	pass through the `_mutable` gate. Checked by parsing rather than by
	remembering, because remembering is what failed."""

	def test_every_oracle_record_mutator_checks_mutable(self):
		cls = _contract_class(SV_TREE, "SkillVerify")
		# _apply is the shared writer; its callers hold the gate.
		# _apply is the shared writer and its two callers hold the gate (asserted
		# separately below). verify_skill is exempt because it CREATES the
		# record it writes: next_id is incremented first and never reused, so
		# the record it reaches is always brand new and there is no prior status
		# to respect. test_verify_skill_can_never_reach_an_existing_record
		# proves that behaviourally rather than leaving it as a claim.
		exempt = {"_apply", "_summary", "__init__", "verify_skill"}
		offenders = []
		for fn in _methods(cls):
			if fn.name in exempt:
				continue
			writes = [w for w in _writes_record_fields(fn) if w[0] in ("record", "bounty")]
			if not writes:
				continue
			if not _calls_named(fn, "_mutable"):
				offenders.append((fn.name, writes[0][2]))
		self.assertEqual(offenders, [])

	def test_every_consumer_record_mutator_checks_mutable(self):
		cls = _contract_class(SC_TREE, "SkillConsumer")
		exempt = {"_summary", "__init__"}
		offenders = []
		for fn in _methods(cls):
			if fn.name in exempt:
				continue
			writes = [w for w in _writes_record_fields(fn) if w[0] == "bounty"]
			if not writes:
				continue
			# post_bounty creates the record, so there is nothing yet to freeze.
			if fn.name == "post_bounty":
				continue
			if not _calls_named(fn, "_mutable"):
				offenders.append((fn.name, writes[0][2]))
		self.assertEqual(offenders, [])

	def test_apply_is_only_called_behind_the_gate(self):
		cls = _contract_class(SV_TREE, "SkillVerify")
		callers = [fn.name for fn in _methods(cls) if _calls_named(fn, "_apply") and fn.name != "_apply"]
		self.assertEqual(sorted(callers), ["resolve_pending", "verify_skill"])
		for fn in _methods(cls):
			if fn.name == "resolve_pending":
				self.assertTrue(_calls_named(fn, "_mutable"))
			if fn.name == "verify_skill":
				self.assertTrue(_calls_named(fn, "get_or_insert_default"))

	def test_owner_methods_never_touch_a_record(self):
		# THE PROPERTY A REVIEWER LOOKS FOR FIRST. There must be no path by
		# which the owner can rewrite, delete or re-level a verification.
		cls = _contract_class(SV_TREE, "SkillVerify")
		owner_methods = [fn for fn in _methods(cls) if _calls_named(fn, "_only_owner")]
		self.assertGreaterEqual(len(owner_methods), 7)
		for fn in owner_methods:
			self.assertEqual(_writes_record_fields(fn), [], fn.name)
			self.assertFalse(_calls_named(fn, "_apply"), fn.name)
			for node in ast.walk(fn):
				if isinstance(node, ast.Attribute) and node.attr in ("verifications", "latest_resolved", "inflight"):
					self.fail(fn.name + " reaches a verification table at line " + str(node.lineno))


class TestNondetHygiene(unittest.TestCase):

	def test_no_closure_captures_self(self):
		self.assertEqual(_nondet_closures_referencing_self(SV_TREE), [])

	def test_helpers_used_by_closures_are_module_level(self):
		names = {n.name for n in SV_TREE.body if isinstance(n, ast.FunctionDef)}
		for required in ("_evaluate", "_score", "_search_url", "_pct", "_level_for", "_axis_of", "_compare_key"):
			self.assertIn(required, names)

	def test_leader_error_is_rerun_not_voted_false(self):
		# Answering False on a leader exception turns one node's transient
		# failure into a genuine disagreement and burns a round. The validator
		# must CALL leader_fn() in that branch.
		src = SOURCE.read_text(encoding="utf8")
		marker = "if not isinstance(leader_result, gl.vm.Return):"
		self.assertIn(marker, src)
		after = src.split(marker, 1)[1][:200]
		self.assertIn("leader_fn()", after)

	def test_validator_reruns_the_whole_evaluation(self):
		# A validator that only inspects the leader's payload has verified
		# nothing. It must produce its own answer.
		src = SOURCE.read_text(encoding="utf8")
		block = src.split("def validator_fn(", 1)[1]
		self.assertIn("_compare_key(leader_fn())", block)

	def test_the_compared_key_is_the_bound_one(self):
		# THE REJECTED VERSION COMPARED _axis_of HERE — one string, with the
		# repo_count and total_bytes that the stored level is checked against
		# riding along uncompared. The validator must compare the key that
		# binds them, and must not fall back to the bare axis.
		src = SOURCE.read_text(encoding="utf8")
		block = src.split("def validator_fn(", 1)[1].split("outcome = gl.vm.run_nondet", 1)[0]
		self.assertIn("return mine == theirs", block)
		self.assertIn("_compare_key(", block)
		self.assertNotIn("_axis_of(", block, "validator compares the unbound axis")

	def test_the_bound_key_reads_both_counts(self):
		# Asserted against the helper rather than the closure, because that is
		# where the binding now lives and a _compare_key that quietly stopped
		# reading a count would restore the hole with the call site intact.
		src = SOURCE.read_text(encoding="utf8")
		block = src.split("def _compare_key(", 1)[1].split("\ndef ", 1)[0]
		for required in ('result.get("repo_count")', 'result.get("total_bytes")'):
			self.assertIn(required, block, "_compare_key does not read " + required)


# ═══════════════════════════════════════════════════════════════════════════
# 2. PURE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

class TestNormalisation(unittest.TestCase):

	def test_username_lowercased(self):
		self.assertEqual(SV._normalize_username("Torvalds"), "torvalds")

	def test_username_trimmed(self):
		self.assertEqual(SV._normalize_username("  torvalds  "), "torvalds")

	def test_username_truncated_at_39(self):
		self.assertEqual(len(SV._normalize_username("a" * 200)), 39)

	def test_username_of_none_is_empty_not_the_word_none(self):
		# If this ever returns "none" again, a missing argument becomes a lookup
		# of a real GitHub account.
		self.assertEqual(SV._normalize_username(None), "")

	def test_skill_lowercased_and_collapsed(self):
		self.assertEqual(SV._normalize_skill("  Jupyter   Notebook "), "jupyter notebook")

	def test_skill_truncated_at_40(self):
		self.assertEqual(len(SV._normalize_skill("x" * 200)), 40)

	def test_display_skill_keeps_case(self):
		self.assertEqual(SV._display_skill("  Jupyter   Notebook "), "Jupyter Notebook")

	def test_case_variants_index_to_one_bucket(self):
		self.assertEqual(SV._normalize_skill("PYTHON"), SV._normalize_skill("python"))
		self.assertEqual(SV._normalize_username("TORVALDS"), SV._normalize_username("torvalds"))


class TestUsernameValidation(unittest.TestCase):

	def ok(self, value):
		self.assertEqual(SV._username_problem(value), "", repr(value))

	def bad(self, value):
		self.assertNotEqual(SV._username_problem(value), "", repr(value))

	def test_plain_name(self):
		self.ok("torvalds")

	def test_mixed_case(self):
		self.ok("Torvalds")

	def test_digits(self):
		self.ok("kenil1710")

	def test_single_hyphen(self):
		self.ok("some-user")

	def test_exactly_39_chars(self):
		self.ok("a" * 39)

	def test_40_chars_refused(self):
		self.bad("a" * 40)

	def test_empty_refused(self):
		self.bad("")

	def test_whitespace_only_refused(self):
		self.bad("   ")

	def test_leading_hyphen_refused(self):
		self.bad("-torvalds")

	def test_trailing_hyphen_refused(self):
		self.bad("torvalds-")

	def test_double_hyphen_refused(self):
		self.bad("tor--valds")

	def test_underscore_refused(self):
		self.bad("tor_valds")

	def test_slash_refused(self):
		# A slash would let a caller escape the `user:` qualifier.
		self.bad("torvalds/linux")

	def test_space_refused(self):
		self.bad("tor valds")

	def test_query_injection_refused(self):
		self.bad("torvalds&q=x")
		self.bad("torvalds language:C")
		self.bad('torvalds"')

	def test_unicode_refused(self):
		self.bad("torvaldß")

	def test_none_refused(self):
		self.bad(None)

	def test_dict_refused(self):
		self.bad({"a": 1})

	def test_int_is_accepted_because_it_is_a_legal_name(self):
		# Deliberate, and worth a named test rather than a surprise: str(12345)
		# is "12345", and an all-digit GitHub username is legal. The validator
		# checks the CHARSET, not the type, so this is accepted and then simply
		# fails to match any user. Refusing it would be refusing a real name.
		self.ok(12345)


class TestSkillValidation(unittest.TestCase):

	def ok(self, value):
		self.assertEqual(SV._skill_problem(value), "", repr(value))

	def bad(self, value):
		self.assertNotEqual(SV._skill_problem(value), "", repr(value))

	def test_python(self):
		self.ok("Python")

	def test_c(self):
		self.ok("C")

	def test_cpp_allowed(self):
		# ALLOWED, and made safe by _pct rather than by being banned. C++ is one
		# of the most claimed skills there is; banning it would be a worse bug
		# than the encoding trap it is meant to avoid.
		self.ok("C++")

	def test_csharp_allowed(self):
		self.ok("C#")

	def test_fsharp_allowed(self):
		self.ok("F#")

	def test_objective_c_allowed(self):
		self.ok("Objective-C")

	def test_multi_word_allowed(self):
		self.ok("Jupyter Notebook")

	def test_dotted_allowed(self):
		self.ok("asp.net")

	def test_underscore_allowed(self):
		self.ok("some_lang")

	def test_empty_refused(self):
		self.bad("")

	def test_whitespace_only_refused(self):
		self.bad("    ")

	def test_too_long_refused(self):
		self.bad("x" * 41)

	def test_exactly_40_allowed(self):
		self.ok("x" * 40)

	def test_quote_refused(self):
		# A quote would close the `language:"…"` value and let the rest of the
		# string become query syntax.
		self.bad('C" OR user:someone')

	def test_ampersand_refused(self):
		self.bad("C&per_page=1")

	def test_colon_refused(self):
		self.bad("language:C")

	def test_newline_refused(self):
		self.bad("C\nlanguage:Python")

	def test_tab_is_collapsed_not_refused(self):
		# A tab is whitespace and collapses away; it never reaches the URL.
		self.assertEqual(SV._normalize_skill("Jupyter\tNotebook"), "jupyter notebook")
		self.ok("Jupyter\tNotebook")

	def test_percent_refused(self):
		# A raw percent would let a caller inject their own encoding.
		self.bad("C%22")

	def test_none_refused(self):
		self.bad(None)

	def test_dict_refused(self):
		self.bad({"skill": "python"})


class TestPercentEncoding(unittest.TestCase):
	"""THE FUNCTION THAT IS THE DIFFERENCE BETWEEN VERIFYING C++ AND VERIFYING C.

	docs/PROBE.md 4 and 5 measured, on chain: `q=user:nlohmann+language:C++`
	answers 200 with ONE repository tagged `C` where the right answer is EIGHT
	tagged `C++`. GitHub does not complain — it answers the wrong question."""

	def test_plain_word_untouched(self):
		self.assertEqual(SV._pct("python"), "python")

	def test_plus_encoded(self):
		self.assertEqual(SV._pct("c++"), "c%2B%2B")

	def test_hash_encoded(self):
		self.assertEqual(SV._pct("c#"), "c%23")

	def test_space_encoded_as_pct20_not_plus(self):
		# `+` as a space is the whole trap. It must never be produced.
		self.assertEqual(SV._pct("jupyter notebook"), "jupyter%20notebook")
		self.assertNotIn("+", SV._pct("jupyter notebook"))

	def test_hyphen_dot_underscore_tilde_untouched(self):
		self.assertEqual(SV._pct("objective-c"), "objective-c")
		self.assertEqual(SV._pct("asp.net"), "asp.net")
		self.assertEqual(SV._pct("a_b~c"), "a_b~c")

	def test_quote_encoded(self):
		self.assertEqual(SV._pct('"'), "%22")

	def test_ampersand_encoded(self):
		self.assertEqual(SV._pct("&"), "%26")

	def test_uppercase_hex(self):
		self.assertEqual(SV._pct("+"), "%2B")

	def test_non_ascii_encoded_per_utf8_byte(self):
		self.assertEqual(SV._pct("é"), "%C3%A9")

	def test_non_string_is_empty(self):
		self.assertEqual(SV._pct(None), "")
		self.assertEqual(SV._pct(5), "")

	def test_output_contains_no_query_syntax(self):
		for hostile in ('a"b', "a&b", "a=b", "a?b", "a#b", "a+b", "a b", "a/b", "a:b"):
			out = SV._pct(hostile)
			for ch in '"&=?#+/: ':
				self.assertNotIn(ch, out, hostile)


class TestSearchUrl(unittest.TestCase):

	def test_shape(self):
		url = SV._search_url("torvalds", "C")
		self.assertEqual(
			url,
			"https://api.github.com/search/repositories?per_page=100&sort=updated"
			"&q=user:torvalds%20language:%22c%22",
		)

	def test_language_is_always_quoted(self):
		# Measured: a multi-word value MUST be quoted (31 repos vs 7), and
		# quoting a single word changes nothing (8 either way). One code path.
		for skill in ("C", "Python", "Jupyter Notebook", "C++"):
			self.assertIn("language:%22", SV._search_url("x", skill))
			self.assertTrue(SV._search_url("x", skill).endswith("%22"))

	def test_qualifiers_separated_by_pct20_never_plus(self):
		url = SV._search_url("torvalds", "C")
		self.assertIn("%20language:", url)
		self.assertNotIn("+", url)

	def test_cpp_encodes_to_the_form_that_works(self):
		# The exact string probe round 5 measured returning 8 C++ repositories.
		self.assertIn("language:%22c%2B%2B%22", SV._search_url("nlohmann", "C++"))

	def test_csharp_encodes(self):
		self.assertIn("language:%22c%23%22", SV._search_url("microsoft", "C#"))

	def test_multi_word_encodes(self):
		self.assertIn("language:%22jupyter%20notebook%22", SV._search_url("jakevdp", "Jupyter Notebook"))

	def test_forks_are_not_requested(self):
		# GitHub's default excludes forks, which closes the "fork forty C repos
		# and score EXPERT" hole. Passing fork:true would reopen it.
		self.assertNotIn("fork", SV._search_url("torvalds", "C"))

	def test_hostile_username_cannot_escape(self):
		# The username is normalised and encoded, so even if validation were
		# bypassed the URL cannot grow a qualifier.
		url = SV._search_url('torvalds"+language:Python+"', "C")
		self.assertEqual(url.count("language:"), 1)

	def test_url_is_deterministic(self):
		self.assertEqual(SV._search_url("Torvalds", "c"), SV._search_url("torvalds", "C"))


class TestLadder(unittest.TestCase):

	def test_rank_ordering(self):
		self.assertEqual(SV._rank("NONE"), 0)
		self.assertEqual(SV._rank("BEGINNER"), 1)
		self.assertEqual(SV._rank("PROFICIENT"), 2)
		self.assertEqual(SV._rank("EXPERT"), 3)

	def test_rank_of_nonsense_is_minus_one(self):
		# NOT 0. NONE is a real level, and "not a level at all" must never
		# silently mean NONE — the failure mode of a typo has to be "nobody
		# passes", never "everybody does".
		for junk in ("expert", "Expert", "", "GURU", None, 3, {}):
			self.assertEqual(SV._rank(junk), -1, repr(junk))

	def test_expert_needs_five_repos_and_bytes(self):
		self.assertEqual(SV._level_for(5, 1000), "EXPERT")
		self.assertEqual(SV._level_for(9, 10 ** 9), "EXPERT")

	def test_five_repos_but_too_few_bytes_is_not_expert(self):
		# The cascade, not a chain of elifs on repo count. Five empty repos are
		# not an expert, and they are not nothing either.
		self.assertEqual(SV._level_for(5, 999), "PROFICIENT")
		self.assertEqual(SV._level_for(5, 499), "BEGINNER")
		self.assertEqual(SV._level_for(5, 0), "BEGINNER")

	def test_proficient_boundaries(self):
		self.assertEqual(SV._level_for(3, 500), "PROFICIENT")
		self.assertEqual(SV._level_for(4, 999), "PROFICIENT")
		self.assertEqual(SV._level_for(3, 499), "BEGINNER")
		self.assertEqual(SV._level_for(2, 10 ** 9), "BEGINNER")

	def test_beginner_boundary(self):
		self.assertEqual(SV._level_for(1, 0), "BEGINNER")
		self.assertEqual(SV._level_for(2, 0), "BEGINNER")

	def test_none_is_zero_repos(self):
		self.assertEqual(SV._level_for(0, 0), "NONE")
		self.assertEqual(SV._level_for(0, 10 ** 12), "NONE")

	def test_negative_and_junk_are_none(self):
		self.assertEqual(SV._level_for(-5, -5), "NONE")
		self.assertEqual(SV._level_for(None, None), "NONE")
		self.assertEqual(SV._level_for("x", "y"), "NONE")

	def test_every_output_is_a_known_level(self):
		for repos in range(0, 12):
			for size in (0, 1, 499, 500, 999, 1000, 10 ** 9):
				self.assertIn(SV._level_for(repos, size), SV.LEVELS)

	def test_ladder_is_monotonic_in_repo_count(self):
		# More repositories at the same volume can never LOWER the level.
		for size in (0, 500, 1000, 10 ** 6):
			ranks = [SV._rank(SV._level_for(n, size)) for n in range(0, 12)]
			self.assertEqual(ranks, sorted(ranks), "size=" + str(size))

	def test_ladder_is_monotonic_in_bytes(self):
		for repos in range(0, 12):
			ranks = [SV._rank(SV._level_for(repos, b)) for b in (0, 100, 499, 500, 999, 1000, 10 ** 9)]
			self.assertEqual(ranks, sorted(ranks), "repos=" + str(repos))


class TestScoreAgainstRealBodies(unittest.TestCase):
	"""Every assertion here runs against a document GitHub actually sent,
	captured 2026-09-07 and cross-checked against what the on-chain probe
	measured for the same query."""

	def test_torvalds_c_is_expert(self):
		out = SV._score(fixture_doc("torvalds_C"), "C")
		self.assertEqual(out["level"], "EXPERT")
		self.assertEqual(out["repo_count"], 8)
		self.assertGreater(out["total_bytes"], 0)

	def test_torvalds_c_matches_the_onchain_probe(self):
		# docs/PROBE.md 4: the chain scored this EXPERT with 8 repositories,
		# and the repo-walk in round 1 independently scored it EXPERT too.
		out = SV._score(fixture_doc("torvalds_C"), "C")
		self.assertEqual((out["level"], out["repo_count"]), ("EXPERT", 8))

	def test_gvanrossum_python_is_expert(self):
		out = SV._score(fixture_doc("gvanrossum_Python"), "Python")
		self.assertEqual(out["level"], "EXPERT")
		self.assertEqual(out["repo_count"], 8)

	def test_kenil1710_javascript_is_expert(self):
		out = SV._score(fixture_doc("kenil1710_JS"), "JavaScript")
		self.assertEqual(out["level"], "EXPERT")
		self.assertEqual(out["repo_count"], 5)

	def test_kenil1710_typescript_is_expert(self):
		out = SV._score(fixture_doc("kenil1710_TS"), "TypeScript")
		self.assertEqual(out["level"], "EXPERT")
		self.assertEqual(out["repo_count"], 6)

	def test_torvalds_haskell_is_none(self):
		out = SV._score(fixture_doc("torvalds_Haskell"), "Haskell")
		self.assertEqual(out["level"], "NONE")
		self.assertEqual(out["repo_count"], 0)
		self.assertEqual(out["total_bytes"], 0)
		self.assertEqual(out["top_repos"], [])

	def test_octocat_html_is_beginner(self):
		out = SV._score(fixture_doc("octocat_HTML"), "HTML")
		self.assertEqual(out["repo_count"], 1)
		self.assertEqual(out["level"], "BEGINNER")

	def test_nlohmann_cpp_is_expert(self):
		out = SV._score(fixture_doc("nlohmann_Cpp"), "C++")
		self.assertEqual(out["level"], "EXPERT")
		self.assertEqual(out["repo_count"], 8)

	# ─────────────────────────────────────────────────────────────────────
	# THE BUG THE PROBE FOUND. docs/PROBE.md 5.
	# ─────────────────────────────────────────────────────────────────────

	def test_unrecognised_language_scores_none(self):
		"""GitHub silently ignores a `language:` qualifier it cannot parse and
		returns the user's WHOLE repository list with a 200. Trusting
		`total_count` therefore certifies anybody as EXPERT in any typo:
		verify_skill("torvalds", "Notalanguage") would have returned EXPERT and
		nothing about the transaction would have looked wrong.

		This is the single most important assertion in the file, because it is
		the one bug in this project that is invisible in every other test."""
		doc = fixture_doc("torvalds_bogus")
		# The document really does come back full — 9 repositories, 200 OK.
		self.assertEqual(len(doc["items"]), 9)
		self.assertEqual(doc["total_count"], 9)
		out = SV._score(doc, "Notalanguage")
		self.assertEqual(out["level"], "NONE")
		self.assertEqual(out["repo_count"], 0)
		# And the discrepancy stays VISIBLE rather than being swallowed.
		self.assertEqual(out["index_count"], 9)

	def test_total_count_is_never_the_score(self):
		doc = fixture_doc("torvalds_bogus")
		out = SV._score(doc, "Notalanguage")
		self.assertNotEqual(out["repo_count"], out["index_count"])

	def test_the_bogus_document_still_scores_c_correctly(self):
		# The same unfiltered response, scored for a language that IS in it.
		# Proves the filter selects rather than merely rejecting everything.
		out = SV._score(fixture_doc("torvalds_bogus"), "C")
		self.assertEqual(out["repo_count"], 8)
		self.assertEqual(out["level"], "EXPERT")

	def test_the_cpp_plus_trap_scores_none(self):
		"""`q=user:nlohmann+language:C++` returns ONE repository, tagged `C`.
		The contract never builds that URL (_pct), but if it somehow did, the
		item re-check is the second line of defence and scores it NONE."""
		doc = fixture_doc("nlohmann_Cpp_trap")
		self.assertEqual(len(doc["items"]), 1)
		self.assertEqual(doc["items"][0]["language"], "C")
		self.assertEqual(SV._score(doc, "C++")["level"], "NONE")

	# ─────────────────────────────────────────────────────────────────────

	def test_case_insensitive_match(self):
		for spelling in ("c", "C", "  c  "):
			self.assertEqual(SV._score(fixture_doc("torvalds_C"), spelling)["repo_count"], 8)

	def test_top_repos_capped_at_three(self):
		out = SV._score(fixture_doc("torvalds_C"), "C")
		self.assertEqual(len(out["top_repos"]), 3)

	def test_top_repos_are_ordered_by_bytes_descending(self):
		doc = {"total_count": 3, "items": [
			{"name": "small", "language": "Go", "size": 1},
			{"name": "big", "language": "Go", "size": 900},
			{"name": "mid", "language": "Go", "size": 50},
		]}
		self.assertEqual(SV._score(doc, "Go")["top_repos"], ["big", "mid", "small"])

	def test_ties_break_on_name_so_validators_cannot_disagree(self):
		doc = {"total_count": 3, "items": [
			{"name": "zeta", "language": "Go", "size": 10},
			{"name": "alpha", "language": "Go", "size": 10},
			{"name": "mike", "language": "Go", "size": 10},
		]}
		self.assertEqual(SV._score(doc, "Go")["top_repos"], ["alpha", "mike", "zeta"])
		# And the ordering is total: shuffling the input cannot change it.
		doc["items"].reverse()
		self.assertEqual(SV._score(doc, "Go")["top_repos"], ["alpha", "mike", "zeta"])

	def test_size_is_kilobytes_times_1024(self):
		doc = {"total_count": 1, "items": [{"name": "r", "language": "Go", "size": 3}]}
		self.assertEqual(SV._score(doc, "Go")["total_bytes"], 3 * 1024)

	def test_null_language_never_matches(self):
		doc = {"total_count": 2, "items": [
			{"name": "a", "language": None, "size": 100},
			{"name": "b", "language": "Go", "size": 100},
		]}
		self.assertEqual(SV._score(doc, "Go")["repo_count"], 1)

	def test_a_null_language_does_not_match_the_skill_none(self):
		# THE SLIP _as_text EXISTS TO CLOSE. str(None) is "None", which
		# lowercases to the legal skill string "none" — so a repository GitHub
		# could not classify would have MATCHED a claim of "none", and a user
		# would have been certified in a language by virtue of GitHub not
		# knowing what their code was. _as_text maps None to "" instead, and ""
		# matches no skill because an empty skill is refused at the door.
		doc = {"total_count": 1, "items": [{"name": "a", "language": None, "size": 100}]}
		self.assertEqual(SV._score(doc, "none")["repo_count"], 0)
		self.assertEqual(SV._score(doc, "Go")["repo_count"], 0)

	def test_boolean_size_is_rejected(self):
		# isinstance(True, int) is True in Python. A JSON `true` in `size` must
		# not become 1 KB.
		doc = {"total_count": 1, "items": [{"name": "a", "language": "Go", "size": True}]}
		self.assertEqual(SV._score(doc, "Go")["total_bytes"], 0)

	def test_string_size_is_rejected(self):
		doc = {"total_count": 1, "items": [{"name": "a", "language": "Go", "size": "900"}]}
		self.assertEqual(SV._score(doc, "Go")["total_bytes"], 0)
		self.assertEqual(SV._score(doc, "Go")["repo_count"], 1)

	def test_missing_size_is_zero_not_an_error(self):
		doc = {"total_count": 1, "items": [{"name": "a", "language": "Go"}]}
		self.assertEqual(SV._score(doc, "Go")["total_bytes"], 0)

	def test_negative_size_clamped(self):
		doc = {"total_count": 1, "items": [{"name": "a", "language": "Go", "size": -5}]}
		self.assertEqual(SV._score(doc, "Go")["total_bytes"], 0)

	def test_non_dict_item_skipped(self):
		doc = {"total_count": 2, "items": ["nonsense", {"name": "a", "language": "Go", "size": 1}]}
		self.assertEqual(SV._score(doc, "Go")["repo_count"], 1)

	def test_missing_items_key(self):
		self.assertEqual(SV._score({"total_count": 5}, "Go")["repo_count"], 0)
		self.assertTrue(SV._score({"total_count": 5}, "Go")["ok"])

	def test_items_not_a_list(self):
		self.assertEqual(SV._score({"items": "nope"}, "Go")["repo_count"], 0)

	def test_non_dict_document_is_not_ok(self):
		for junk in ([], "text", None, 5):
			self.assertFalse(SV._score(junk, "Go")["ok"], repr(junk))

	def test_scan_is_capped_at_100_items(self):
		doc = {"total_count": 500, "items": [
			{"name": "r%d" % i, "language": "Go", "size": 10} for i in range(300)
		]}
		self.assertEqual(SV._score(doc, "Go")["repo_count"], 100)

	def test_the_100_cap_never_changes_a_level(self):
		# The ladder saturates at 5 repositories, so a user with 300 matching
		# repositories and a user with 100 are both EXPERT. The cap is a compute
		# bound, not a scoring decision.
		doc = {"total_count": 500, "items": [
			{"name": "r%d" % i, "language": "Go", "size": 10} for i in range(300)
		]}
		self.assertEqual(SV._score(doc, "Go")["level"], "EXPERT")

	def test_repo_name_truncated(self):
		doc = {"total_count": 1, "items": [{"name": "n" * 500, "language": "Go", "size": 1}]}
		self.assertEqual(len(SV._score(doc, "Go")["top_repos"][0]), 100)

	def test_incomplete_results_is_carried(self):
		self.assertTrue(SV._score({"items": [], "incomplete_results": True}, "Go")["incomplete"])
		self.assertFalse(SV._score({"items": []}, "Go")["incomplete"])

	def test_score_is_deterministic_across_repeated_calls(self):
		doc = fixture_doc("torvalds_C")
		first = SV._score(doc, "C")
		for _ in range(5):
			self.assertEqual(SV._score(doc, "C"), first)


class TestContentHash(unittest.TestCase):

	def test_stable_across_calls(self):
		a = SV._content_hash("torvalds", "C", "EXPERT", 8, 999)
		b = SV._content_hash("torvalds", "C", "EXPERT", 8, 999)
		self.assertEqual(a, b)

	def test_sixteen_hex_chars(self):
		h = SV._content_hash("torvalds", "C", "EXPERT", 8, 999)
		self.assertEqual(len(h), 16)
		int(h, 16)

	def test_every_field_changes_it(self):
		base = SV._content_hash("torvalds", "C", "EXPERT", 8, 999)
		self.assertNotEqual(base, SV._content_hash("gvanrossum", "C", "EXPERT", 8, 999))
		self.assertNotEqual(base, SV._content_hash("torvalds", "Go", "EXPERT", 8, 999))
		self.assertNotEqual(base, SV._content_hash("torvalds", "C", "BEGINNER", 8, 999))
		self.assertNotEqual(base, SV._content_hash("torvalds", "C", "EXPERT", 9, 999))
		self.assertNotEqual(base, SV._content_hash("torvalds", "C", "EXPERT", 8, 1000))

	def test_boundary_shifting_cannot_forge_a_collision(self):
		# A hash built by plain concatenation collides when a character moves
		# across a field boundary. The \x1f separator cannot occur in a
		# normalised username or skill, so this pair must differ.
		self.assertNotEqual(
			SV._content_hash("ab", "c", "NONE", 0, 0),
			SV._content_hash("a", "bc", "NONE", 0, 0),
		)

	def test_normalisation_is_applied_before_hashing(self):
		self.assertEqual(
			SV._content_hash("Torvalds", "  C  ", "EXPERT", 8, 999),
			SV._content_hash("torvalds", "c", "EXPERT", 8, 999),
		)

	def test_fnv_matches_the_reference_vector(self):
		# FNV-1a 64-bit of "a" is 0xaf63dc4c8601ec8c. Written out by hand
		# because Python's hash() is seeded per process and leader and
		# validators would disagree for no reason at all.
		self.assertEqual(SV._fnv("a"), "af63dc4c8601ec8c")

	def test_fnv_of_empty_is_empty(self):
		self.assertEqual(SV._fnv(""), "")

	def test_fnv_of_non_string_is_empty(self):
		self.assertEqual(SV._fnv(None), "")

	def test_fnv_handles_unicode(self):
		self.assertEqual(len(SV._fnv("héllo")), 16)


class TestEvaluateClassification(unittest.TestCase):
	"""Rule 4: a full rate-limit bucket is not an answer. Scoring a 403 as NONE
	would certify a working developer as unskilled, permanently, on chain."""

	def setUp(self):
		reset_world()

	def run_eval(self, status, body):
		FETCH_QUEUE.append((status, body))
		return SV._evaluate("torvalds", "C")

	def test_200_produces_a_level(self):
		out = self.run_eval(200, fixture_body("torvalds_C"))
		self.assertEqual(out["axis"], "EXPERT")

	def test_403_is_unavailable_not_none(self):
		out = self.run_eval(403, RATE_LIMIT_BODY)
		self.assertEqual(out["axis"], "UNAVAILABLE")
		self.assertNotEqual(out["axis"], "NONE")

	def test_429_is_unavailable(self):
		self.assertEqual(self.run_eval(429, "{}")["axis"], "UNAVAILABLE")

	def test_500_is_unavailable(self):
		self.assertEqual(self.run_eval(500, "oops")["axis"], "UNAVAILABLE")

	def test_502_is_unavailable(self):
		self.assertEqual(self.run_eval(502, "<html>")["axis"], "UNAVAILABLE")

	def test_422_is_no_such_user_and_is_permanent(self):
		out = self.run_eval(422, fixture_body("missing_user"))
		self.assertEqual(out["axis"], "NO_SUCH_USER")

	def test_422_is_distinguished_from_403(self):
		# The distinction that matters: one is permanent and every validator
		# sees it identically, the other clears in a minute.
		self.assertNotEqual(
			self.run_eval(422, fixture_body("missing_user"))["axis"],
			self.run_eval(403, RATE_LIMIT_BODY)["axis"],
		)

	def test_404_is_unavailable_not_a_score(self):
		self.assertEqual(self.run_eval(404, '{"message":"Not Found"}')["axis"], "UNAVAILABLE")

	def test_200_with_non_json_is_unavailable(self):
		# An interstitial or truncated body is not an answer; it is retried.
		self.assertEqual(self.run_eval(200, "<html>maintenance</html>")["axis"], "UNAVAILABLE")

	def test_200_with_a_json_array_is_unavailable(self):
		self.assertEqual(self.run_eval(200, "[1,2,3]")["axis"], "UNAVAILABLE")

	def test_connection_failure_is_unavailable(self):
		FETCH_QUEUE.append((RuntimeError("connection reset"), ""))
		self.assertEqual(SV._evaluate("torvalds", "C")["axis"], "UNAVAILABLE")

	def test_evaluate_never_raises_for_any_status(self):
		for status in (0, 100, 200, 301, 400, 401, 403, 404, 418, 422, 429, 500, 503, 999):
			FETCH_QUEUE.append((status, "{}"))
			SV._evaluate("torvalds", "C")

	def test_evaluate_hits_the_expected_url(self):
		self.run_eval(200, fixture_body("torvalds_C"))
		self.assertEqual(FETCH_LOG[-1], SV._search_url("torvalds", "C"))

	def test_axis_of_rejects_unknown_values(self):
		self.assertEqual(SV._axis_of({"axis": "GURU"}), "UNAVAILABLE")
		self.assertEqual(SV._axis_of({}), "UNAVAILABLE")
		self.assertEqual(SV._axis_of(None), "UNAVAILABLE")
		self.assertEqual(SV._axis_of("EXPERT"), "UNAVAILABLE")

	def test_axis_of_accepts_every_declared_value(self):
		for value in SV.AXIS_VALUES:
			self.assertEqual(SV._axis_of({"axis": value}), value)


class TestVerifySkillHappyPath(unittest.TestCase):

	def setUp(self):
		self.c = new_oracle()

	def test_resolves_and_returns_a_level(self):
		as_sender(ALICE)
		queue_ok("torvalds_C")
		out = jload(self.c.verify_skill("torvalds", "C"))
		self.assertTrue(out["ok"])
		self.assertEqual(out["verification_id"], 1)
		self.assertEqual(out["status"], "RESOLVED")
		self.assertEqual(out["level"], "EXPERT")
		self.assertEqual(out["repo_count"], 8)

	def test_ids_start_at_one_so_zero_can_mean_absent(self):
		as_sender(ALICE)
		queue_ok("torvalds_C")
		self.assertEqual(jload(self.c.verify_skill("torvalds", "C"))["verification_id"], 1)

	def test_record_is_readable(self):
		as_sender(ALICE)
		queue_ok("torvalds_C")
		self.c.verify_skill("Torvalds", "c")
		row = jload(self.c.get_verification(1))
		self.assertTrue(row["found"])
		self.assertEqual(row["github_username"], "torvalds")
		self.assertEqual(row["skill"], "c")
		self.assertEqual(row["username_display"], "Torvalds")
		self.assertEqual(row["level"], "EXPERT")
		self.assertEqual(row["level_rank"], 3)
		self.assertEqual(row["verified_by"], str(ALICE))
		self.assertEqual(len(row["top_repos"]), 3)

	def test_content_hash_is_present_and_matches_the_fields(self):
		as_sender(ALICE)
		queue_ok("torvalds_C")
		self.c.verify_skill("torvalds", "C")
		row = jload(self.c.get_verification(1))
		self.assertNotEqual(row["content_hash"], "")
		self.assertEqual(
			row["content_hash"],
			SV._content_hash(row["github_username"], row["skill"], row["level"],
				row["repo_count"], int(row["total_bytes"])),
		)

	def test_bytes_basis_is_recorded_on_the_record(self):
		# The record says what its own number MEANS. `total_bytes` is repository
		# size, not a Linguist byte count, and saying so beats overstating by 4x
		# in silence (docs/PROBE.md 7).
		as_sender(ALICE)
		queue_ok("torvalds_C")
		self.c.verify_skill("torvalds", "C")
		self.assertEqual(jload(self.c.get_verification(1))["bytes_basis"], "github_repo_size_kb")
		self.assertEqual(jload(self.c.get_config())["bytes_basis"], "github_repo_size_kb")

	def test_none_level_for_a_skill_the_user_lacks(self):
		as_sender(ALICE)
		queue_ok("torvalds_Haskell")
		out = jload(self.c.verify_skill("torvalds", "Haskell"))
		self.assertEqual(out["level"], "NONE")
		self.assertEqual(out["repo_count"], 0)
		self.assertEqual(out["status"], "RESOLVED")

	def test_bogus_language_resolves_to_none(self):
		# End to end, through the whole contract: the probe's bug cannot reach
		# a stored EXPERT.
		as_sender(ALICE)
		queue_ok("torvalds_bogus")
		out = jload(self.c.verify_skill("torvalds", "Notalanguage"))
		self.assertEqual(out["level"], "NONE")
		self.assertEqual(jload(self.c.get_verification(1))["index_count"], 9)

	def test_missing_user_resolves_none_with_user_found_false(self):
		as_sender(ALICE)
		queue_ok("missing_user")
		out = jload(self.c.verify_skill("no-such-user-skillverify", "Python"))
		self.assertEqual(out["status"], "RESOLVED")
		self.assertEqual(out["level"], "NONE")
		self.assertFalse(out["user_found"])

	def test_stats_move(self):
		as_sender(ALICE)
		queue_ok("torvalds_C")
		self.c.verify_skill("torvalds", "C")
		s = jload(self.c.get_stats())
		self.assertEqual(s["total_verifications"], 1)
		self.assertEqual(s["resolved"], 1)
		self.assertEqual(s["pending"], 0)
		self.assertEqual(s["users_verified"], 1)
		self.assertEqual(s["skills_verified"], 1)
		self.assertEqual(s["pairs_verified"], 1)

	def test_distinct_counters_do_not_double_count(self):
		as_sender(ALICE)
		queue_ok("torvalds_C")
		self.c.verify_skill("torvalds", "C")
		clock_at(400)
		as_sender(BOB)
		queue_ok("torvalds_Haskell")
		self.c.verify_skill("torvalds", "Haskell")
		s = jload(self.c.get_stats())
		self.assertEqual(s["users_verified"], 1)   # same user
		self.assertEqual(s["skills_verified"], 2)  # two skills
		self.assertEqual(s["pairs_verified"], 2)

	def test_no_transfer_when_the_fee_is_zero(self):
		as_sender(ALICE, 0)
		queue_ok("torvalds_C")
		self.c.verify_skill("torvalds", "C")
		self.assertEqual(TRANSFERS, [])


class TestVerifySkillRefundsNeverReverts(unittest.TestCase):
	"""RULE 1, AND THE MOST IMPORTANT CLASS IN THIS FILE.

	GenVM rolls back contract STATE on a UserError but does NOT return the value
	that rode in with the call — it stays in the contract, unaccounted for and
	unreachable. Every rejection below must therefore be a SUCCESSFUL
	transaction that refunds, never a raise."""

	def setUp(self):
		self.c = new_oracle()

	def reject(self, *args, value=5 * GEN, sender=ALICE):
		as_sender(sender, value)
		before = len(TRANSFERS)
		out = jload(self.c.verify_skill(*args))
		self.assertFalse(out["ok"], out)
		# The money came back, in full, in the same transaction.
		self.assertEqual(TRANSFERS[before:], [(str(sender), value)], out["reason"])
		self.assertEqual(int(out["refunded"]), value)
		return out

	def test_empty_username_refunds(self):
		self.reject("", "Python")

	def test_long_username_refunds(self):
		self.reject("a" * 40, "Python")

	def test_hyphen_username_refunds(self):
		self.reject("-bad", "Python")

	def test_slash_username_refunds(self):
		self.reject("a/b", "Python")

	def test_empty_skill_refunds(self):
		self.reject("torvalds", "")

	def test_long_skill_refunds(self):
		self.reject("torvalds", "x" * 41)

	def test_injection_skill_refunds(self):
		self.reject("torvalds", 'C" OR user:x')

	def test_colon_skill_refunds(self):
		self.reject("torvalds", "language:C")

	def test_paused_refunds(self):
		as_sender(OWNER)
		self.c.pause()
		self.reject("torvalds", "Python")

	def test_underpaid_refunds_everything(self):
		as_sender(OWNER)
		self.c.set_fee(GEN)
		as_sender(ALICE, GEN // 2)
		before = len(TRANSFERS)
		out = jload(self.c.verify_skill("torvalds", "C"))
		self.assertFalse(out["ok"])
		self.assertEqual(TRANSFERS[before:], [(str(ALICE), GEN // 2)])

	def test_rate_limited_refunds(self):
		as_sender(ALICE, 0)
		queue_ok("torvalds_C")
		self.c.verify_skill("torvalds", "C")
		self.reject("gvanrossum", "Python")  # same wallet, inside the cooldown

	def test_in_flight_duplicate_refunds(self):
		as_sender(ALICE, 0)
		queue_raw(403, RATE_LIMIT_BODY)
		self.assertEqual(jload(self.c.verify_skill("torvalds", "C"))["status"], "PENDING")
		clock_at(400)
		self.reject("torvalds", "C", sender=BOB)

	def test_no_rejection_path_ever_raises(self):
		# The property, stated directly: for a wide sweep of hostile inputs,
		# verify_skill either succeeds or refuses — it never raises.
		hostile = ["", " ", "a" * 100, "-x", "x-", "a--b", "a/b", "a b", "a:b",
			'a"b', "a&b", None, {"x": 1}, 12345, b"bytes", "\n", "\x00"]
		for user in hostile:
			for skill in hostile:
				as_sender(CAROL, 1)
				try:
					out = jload(self.c.verify_skill(user, skill))
				except Exception as exc:
					self.fail("verify_skill raised for (%r, %r): %r" % (user, skill, exc))
				self.assertIn("ok", out)
				if not out["ok"]:
					self.assertEqual(int(out["refunded"]), 1)

	def test_overpayment_is_returned_as_change(self):
		as_sender(OWNER)
		self.c.set_fee(GEN)
		as_sender(ALICE, 3 * GEN)
		queue_ok("torvalds_C")
		before = len(TRANSFERS)
		out = jload(self.c.verify_skill("torvalds", "C"))
		self.assertTrue(out["ok"])
		self.assertEqual(int(out["change_returned"]), 2 * GEN)
		self.assertEqual(TRANSFERS[before:], [(str(ALICE), 2 * GEN)])

	def test_exact_payment_returns_no_change(self):
		as_sender(OWNER)
		self.c.set_fee(GEN)
		as_sender(ALICE, GEN)
		queue_ok("torvalds_C")
		before = len(TRANSFERS)
		self.assertTrue(jload(self.c.verify_skill("torvalds", "C"))["ok"])
		self.assertEqual(TRANSFERS[before:], [])

	def test_a_refused_call_writes_no_state(self):
		# The counters must count things that HAPPENED. A rejection is not one.
		before = jload(self.c.get_stats())
		self.reject("", "Python")
		after = jload(self.c.get_stats())
		for key in ("total_verifications", "resolved", "pending", "stalled",
				"users_verified", "skills_verified", "next_id"):
			self.assertEqual(before[key], after[key], key)

	def test_a_refused_call_does_not_start_the_cooldown(self):
		# Being refused must not cost a wallet its next 300 seconds.
		self.reject("", "Python", sender=CAROL)
		as_sender(CAROL, 0)
		queue_ok("torvalds_C")
		self.assertTrue(jload(self.c.verify_skill("torvalds", "C"))["ok"])


class TestPendingLifecycle(unittest.TestCase):
	"""RULE 4 END TO END. A verification that met a full rate-limit bucket is
	DURABLY RECORDED and re-resolvable. It is never scored, because scoring an
	empty bucket as NONE would certify a real developer as unskilled."""

	def setUp(self):
		self.c = new_oracle()

	def pend(self, user="torvalds", skill="C", sender=ALICE):
		as_sender(sender, 0)
		queue_raw(403, RATE_LIMIT_BODY)
		return jload(self.c.verify_skill(user, skill))

	def test_403_lands_pending_not_none(self):
		out = self.pend()
		self.assertTrue(out["ok"])
		self.assertEqual(out["status"], "PENDING")
		self.assertEqual(out["level"], "")

	def test_pending_record_carries_no_content_hash(self):
		self.pend()
		self.assertEqual(jload(self.c.get_verification(1))["content_hash"], "")

	def test_pending_record_records_why(self):
		self.pend()
		self.assertIn("403", jload(self.c.get_verification(1))["last_reason"])

	def test_pending_counts_as_pending_in_stats(self):
		self.pend()
		s = jload(self.c.get_stats())
		self.assertEqual(s["pending"], 1)
		self.assertEqual(s["resolved"], 0)
		self.assertEqual(s["total_verifications"], 1)

	def test_pending_holds_the_in_flight_slot(self):
		self.pend()
		self.assertEqual(jload(self.c.get_latest("torvalds", "C"))["pending_id"], 1)

	def test_resolve_pending_succeeds_when_the_bucket_clears(self):
		self.pend()
		queue_ok("torvalds_C")
		out = jload(self.c.resolve_pending(1))
		self.assertTrue(out["ok"])
		self.assertEqual(out["status"], "RESOLVED")
		self.assertEqual(out["level"], "EXPERT")

	def test_resolve_pending_releases_the_slot(self):
		self.pend()
		queue_ok("torvalds_C")
		self.c.resolve_pending(1)
		self.assertEqual(jload(self.c.get_latest("torvalds", "C"))["pending_id"], -1)

	def test_resolve_pending_fixes_the_stats(self):
		self.pend()
		queue_ok("torvalds_C")
		self.c.resolve_pending(1)
		s = jload(self.c.get_stats())
		self.assertEqual(s["pending"], 0)
		self.assertEqual(s["resolved"], 1)

	def test_resolve_pending_is_permissionless(self):
		# A record belongs to whoever needs it resolved, not to whoever
		# submitted it — otherwise one absent address strands it forever.
		self.pend(sender=ALICE)
		as_sender(CAROL, 0)
		queue_ok("torvalds_C")
		self.assertTrue(jload(self.c.resolve_pending(1))["ok"])

	def test_resolve_pending_can_be_retried_after_another_403(self):
		self.pend()
		queue_raw(403, RATE_LIMIT_BODY)
		self.assertTrue(jload(self.c.resolve_pending(1))["ok"])
		self.assertEqual(jload(self.c.get_verification(1))["status"], "PENDING")
		self.assertEqual(jload(self.c.get_verification(1))["attempts"], 2)
		queue_ok("torvalds_C")
		self.assertEqual(jload(self.c.resolve_pending(1))["level"], "EXPERT")

	def test_resolve_pending_runs_during_a_pause(self):
		# Pause stops NEW risk arriving. It must never trap a record in a state
		# it cannot leave — that would let the owner make a username
		# permanently unverifiable, which is exactly the power pause excludes.
		self.pend()
		as_sender(OWNER)
		self.c.pause()
		queue_ok("torvalds_C")
		self.assertTrue(jload(self.c.resolve_pending(1))["ok"])

	def test_resolve_pending_unknown_id_refuses_without_raising(self):
		self.assertFalse(jload(self.c.resolve_pending(999))["ok"])
		self.assertFalse(jload(self.c.resolve_pending(-1))["ok"])
		self.assertFalse(jload(self.c.resolve_pending(0))["ok"])

	def test_a_second_request_for_the_same_pair_is_refused(self):
		self.pend()
		clock_at(400)
		as_sender(BOB, 0)
		out = jload(self.c.verify_skill("torvalds", "C"))
		self.assertFalse(out["ok"])
		self.assertIn("in flight", out["reason"])

	def test_a_different_pair_is_not_blocked(self):
		self.pend()
		clock_at(400)
		as_sender(BOB, 0)
		queue_ok("torvalds_Haskell")
		self.assertTrue(jload(self.c.verify_skill("torvalds", "Haskell"))["ok"])

	def test_the_slot_frees_once_resolved_and_a_re_verify_is_allowed(self):
		self.pend()
		queue_ok("torvalds_C")
		self.c.resolve_pending(1)
		clock_at(400)
		as_sender(BOB, 0)
		queue_ok("torvalds_C")
		out = jload(self.c.verify_skill("torvalds", "C"))
		self.assertTrue(out["ok"])
		self.assertEqual(out["verification_id"], 2)


class TestSettleStalled(unittest.TestCase):
	"""The backstop. Without it, a pair whose verification met a permanently
	broken GitHub would hold its in-flight slot forever and NOBODY could ever
	verify that username and skill again — the anti-duplicate guard would have
	become a denial of service."""

	def setUp(self):
		self.c = new_oracle()
		as_sender(ALICE, 0)
		queue_raw(403, RATE_LIMIT_BODY)
		self.c.verify_skill("torvalds", "C")

	def test_refused_inside_the_window(self):
		out = jload(self.c.settle_stalled(1))
		self.assertFalse(out["ok"])
		self.assertIn("left", out["reason"])

	def test_allowed_after_the_window(self):
		clock_at(3601)
		out = jload(self.c.settle_stalled(1))
		self.assertTrue(out["ok"])
		self.assertEqual(out["status"], "STALLED")

	def test_stalled_record_carries_no_level_and_no_hash(self):
		# A hash certifies a MEASURED result, and there was never a
		# measurement. Emitting one over an empty level would give an unverified
		# record a verified record's shape.
		clock_at(3601)
		self.c.settle_stalled(1)
		row = jload(self.c.get_verification(1))
		self.assertEqual(row["level"], "")
		self.assertEqual(row["content_hash"], "")

	def test_stalled_releases_the_slot(self):
		clock_at(3601)
		self.c.settle_stalled(1)
		self.assertEqual(jload(self.c.get_latest("torvalds", "C"))["pending_id"], -1)

	def test_the_pair_becomes_verifiable_again(self):
		clock_at(3601)
		self.c.settle_stalled(1)
		as_sender(BOB, 0)
		queue_ok("torvalds_C")
		self.assertTrue(jload(self.c.verify_skill("torvalds", "C"))["ok"])

	def test_settle_stalled_is_permissionless(self):
		clock_at(3601)
		as_sender(CAROL, 0)
		self.assertTrue(jload(self.c.settle_stalled(1))["ok"])

	def test_settle_stalled_runs_during_a_pause(self):
		clock_at(3601)
		as_sender(OWNER)
		self.c.pause()
		as_sender(CAROL, 0)
		self.assertTrue(jload(self.c.settle_stalled(1))["ok"])

	def test_stats_move_to_stalled(self):
		clock_at(3601)
		self.c.settle_stalled(1)
		s = jload(self.c.get_stats())
		self.assertEqual(s["stalled"], 1)
		self.assertEqual(s["pending"], 0)

	def test_unknown_id_refuses_without_raising(self):
		self.assertFalse(jload(self.c.settle_stalled(999))["ok"])

	def test_a_resolved_record_cannot_be_stalled(self):
		queue_ok("torvalds_C")
		self.c.resolve_pending(1)
		clock_at(99999)
		out = jload(self.c.settle_stalled(1))
		self.assertFalse(out["ok"])
		self.assertEqual(jload(self.c.get_verification(1))["status"], "RESOLVED")

	def test_the_window_is_the_one_frozen_on_the_record(self):
		# An owner who lengthens the default afterwards cannot reach backwards
		# and keep an existing record in flight.
		as_sender(OWNER)
		self.c.set_resolve_window(30 * 86400)
		clock_at(3601)
		as_sender(CAROL, 0)
		self.assertTrue(jload(self.c.settle_stalled(1))["ok"])

	def test_settle_stalled_at_is_reported_before_it_is_due(self):
		row = jload(self.c.get_verification(1))
		self.assertEqual(row["settle_stalled_at"], row["requested_at"] + 3600)


class TestTerminalRecordsAreUnreachable(unittest.TestCase):
	"""RULE 5, BEHAVIOURALLY. The AST scan proves every mutator holds the gate;
	this proves the gate actually holds."""

	def setUp(self):
		self.c = new_oracle()
		as_sender(ALICE, 0)
		queue_ok("torvalds_C")
		self.c.verify_skill("torvalds", "C")
		self.before = jload(self.c.get_verification(1))

	# age_seconds and stale are DERIVED at read time, not stored, so they move
	# with the clock by design. Everything else is the record.
	DERIVED = ("age_seconds", "stale")

	def stored(self, row):
		return {k: v for k, v in row.items() if k not in self.DERIVED}

	def unchanged(self):
		self.assertEqual(self.stored(jload(self.c.get_verification(1))), self.stored(self.before))

	def test_resolve_pending_refuses_a_resolved_record(self):
		out = jload(self.c.resolve_pending(1))
		self.assertFalse(out["ok"])
		self.assertIn("can never change", out["reason"])
		self.unchanged()

	def test_settle_stalled_refuses_a_resolved_record(self):
		clock_at(999999)
		self.assertFalse(jload(self.c.settle_stalled(1))["ok"])
		self.unchanged()

	def test_the_owner_cannot_change_a_level(self):
		# There is no method that can. Enumerated rather than asserted in
		# prose: every owner entry point is called and the record is compared.
		as_sender(OWNER, 0)
		self.c.set_fee(GEN)
		self.c.set_cooldown(0)
		self.c.set_resolve_window(60)
		self.c.set_freshness_window(86400)
		self.c.pause()
		self.c.unpause()
		self.unchanged()

	def test_the_owner_cannot_stall_a_resolved_record(self):
		as_sender(OWNER, 0)
		clock_at(999999)
		self.assertFalse(jload(self.c.settle_stalled(1))["ok"])
		self.unchanged()

	def test_a_stalled_record_is_equally_frozen(self):
		c = new_oracle()
		as_sender(ALICE, 0)
		queue_raw(403, RATE_LIMIT_BODY)
		c.verify_skill("gvanrossum", "Python")
		clock_at(3601)
		c.settle_stalled(1)
		frozen = self.stored(jload(c.get_verification(1)))
		queue_ok("gvanrossum_Python")
		self.assertFalse(jload(c.resolve_pending(1))["ok"])
		self.assertFalse(jload(c.settle_stalled(1))["ok"])
		self.assertEqual(self.stored(jload(c.get_verification(1))), frozen)

	def test_re_verifying_creates_a_new_record_and_leaves_the_old_one(self):
		clock_at(400)
		as_sender(BOB, 0)
		queue_ok("torvalds_Haskell")   # a different answer for the same pair
		FETCH_QUEUE.clear(); VALIDATOR_QUEUE.clear()
		queue_ok("torvalds_C")
		out = jload(self.c.verify_skill("torvalds", "C"))
		self.assertEqual(out["verification_id"], 2)
		self.unchanged()

	def test_verify_skill_can_never_reach_an_existing_record(self):
		# next_id is incremented before the record is touched and never reused,
		# so the handle verify_skill writes through is always brand new. Proved
		# by running twenty verifications and asserting every id is distinct and
		# every earlier record is untouched.
		c = new_oracle()
		as_sender(OWNER, 0)
		c.set_cooldown(0)
		seen = []
		snapshots = {}
		for i in range(20):
			as_sender(ALICE, 0)
			queue_ok("torvalds_C")
			out = jload(c.verify_skill("user%d" % i, "C"))
			seen.append(out["verification_id"])
			snapshots[out["verification_id"]] = self.stored(jload(c.get_verification(out["verification_id"])))
		self.assertEqual(len(set(seen)), 20)
		for vid, snap in snapshots.items():
			self.assertEqual(self.stored(jload(c.get_verification(vid))), snap)


class TestRateLimit(unittest.TestCase):

	def setUp(self):
		self.c = new_oracle()

	def test_second_request_inside_the_window_is_refused(self):
		as_sender(ALICE, 0)
		queue_ok("torvalds_C")
		self.c.verify_skill("torvalds", "C")
		out = jload(self.c.verify_skill("gvanrossum", "Python"))
		self.assertFalse(out["ok"])
		self.assertIn("rate limited", out["reason"])

	def test_allowed_after_300_seconds(self):
		as_sender(ALICE, 0)
		queue_ok("torvalds_C")
		self.c.verify_skill("torvalds", "C")
		clock_at(300)
		queue_ok("gvanrossum_Python")
		self.assertTrue(jload(self.c.verify_skill("gvanrossum", "Python"))["ok"])

	def test_refused_at_299_seconds(self):
		as_sender(ALICE, 0)
		queue_ok("torvalds_C")
		self.c.verify_skill("torvalds", "C")
		clock_at(299)
		self.assertFalse(jload(self.c.verify_skill("gvanrossum", "Python"))["ok"])

	def test_the_limit_is_per_wallet(self):
		as_sender(ALICE, 0)
		queue_ok("torvalds_C")
		self.c.verify_skill("torvalds", "C")
		as_sender(BOB, 0)
		queue_ok("gvanrossum_Python")
		self.assertTrue(jload(self.c.verify_skill("gvanrossum", "Python"))["ok"])

	def test_a_fresh_wallet_is_not_rate_limited_by_the_zero_default(self):
		# The trap the TreeMap stub exists to catch: a scalar map answers 0 for
		# a key that was never written, so a naive `is not None` check would
		# rate-limit every wallet's FIRST request forever.
		for wallet in (ALICE, BOB, CAROL):
			as_sender(wallet, 0)
			queue_ok("torvalds_C")
			self.assertTrue(jload(self.c.verify_skill("u" + str(wallet)[-4:], "C"))["ok"], str(wallet))

	def test_cooldown_zero_disables_the_limit(self):
		as_sender(OWNER, 0)
		self.c.set_cooldown(0)
		for i in range(3):
			as_sender(ALICE, 0)
			queue_ok("torvalds_C")
			self.assertTrue(jload(self.c.verify_skill("user%d" % i, "C"))["ok"])


class TestIsVerified(unittest.TestCase):
	"""THE COMPOSABILITY PRIMITIVE. It must never raise, for any input — a gate
	that reverts instead of answering cannot be used inside a payable method
	without taking the caller's value with it."""

	def setUp(self):
		self.c = new_oracle()
		as_sender(OWNER, 0)
		self.c.set_cooldown(0)
		as_sender(ALICE, 0)
		queue_ok("torvalds_C")
		self.c.verify_skill("torvalds", "C")           # EXPERT
		queue_ok("octocat_HTML")
		self.c.verify_skill("octocat", "HTML")         # BEGINNER
		queue_ok("torvalds_Haskell")
		self.c.verify_skill("torvalds", "Haskell")     # NONE

	def test_expert_meets_every_level(self):
		for level in ("NONE", "BEGINNER", "PROFICIENT", "EXPERT"):
			self.assertTrue(self.c.is_verified("torvalds", "C", level), level)

	def test_beginner_meets_only_the_bottom_two(self):
		self.assertTrue(self.c.is_verified("octocat", "HTML", "NONE"))
		self.assertTrue(self.c.is_verified("octocat", "HTML", "BEGINNER"))
		self.assertFalse(self.c.is_verified("octocat", "HTML", "PROFICIENT"))
		self.assertFalse(self.c.is_verified("octocat", "HTML", "EXPERT"))

	def test_none_meets_only_none(self):
		self.assertTrue(self.c.is_verified("torvalds", "Haskell", "NONE"))
		self.assertFalse(self.c.is_verified("torvalds", "Haskell", "BEGINNER"))

	def test_unknown_pair_is_false(self):
		self.assertFalse(self.c.is_verified("nobody", "Cobol", "BEGINNER"))

	def test_case_insensitive(self):
		self.assertTrue(self.c.is_verified("TORVALDS", "c", "EXPERT"))
		self.assertTrue(self.c.is_verified("  Torvalds  ", "  C  ", "EXPERT"))

	def test_a_typo_in_min_level_denies_rather_than_admits(self):
		# The failure mode of a typo must be "nobody passes", never "everybody
		# does". This is why _rank returns -1 and not 0.
		for junk in ("expert", "Expert", "EXPERTT", "", "GURU", "none", None, 3, {}):
			self.assertFalse(self.c.is_verified("torvalds", "C", junk), repr(junk))

	def test_never_raises_for_hostile_input(self):
		hostile = ["", " ", "a" * 200, None, {"x": 1}, 5, b"z", "\x00", "a/b", 'a"b']
		for user in hostile:
			for skill in hostile:
				for level in hostile + ["EXPERT"]:
					try:
						self.assertIsInstance(self.c.is_verified(user, skill, level), bool)
					except Exception as exc:
						self.fail("is_verified raised for %r/%r/%r: %r" % (user, skill, level, exc))

	def test_a_pending_verification_does_not_satisfy_it(self):
		c = new_oracle()
		as_sender(ALICE, 0)
		queue_raw(403, RATE_LIMIT_BODY)
		c.verify_skill("torvalds", "C")
		self.assertFalse(c.is_verified("torvalds", "C", "BEGINNER"))

	def test_a_stalled_verification_does_not_satisfy_it(self):
		c = new_oracle()
		as_sender(ALICE, 0)
		queue_raw(403, RATE_LIMIT_BODY)
		c.verify_skill("torvalds", "C")
		clock_at(3601)
		c.settle_stalled(1)
		self.assertFalse(c.is_verified("torvalds", "C", "BEGINNER"))

	def test_the_newest_resolved_record_wins(self):
		# Re-verify the same pair with a weaker result; the gate must follow.
		clock_at(400)
		as_sender(BOB, 0)
		queue_ok("torvalds_bogus")
		self.c.verify_skill("torvalds", "Notalanguage")
		queue_ok("octocat_HTML")
		# octocat/HTML re-verified as itself — still BEGINNER.
		self.c.verify_skill("octocat", "HTML")
		self.assertTrue(self.c.is_verified("octocat", "HTML", "BEGINNER"))
		self.assertFalse(self.c.is_verified("octocat", "HTML", "EXPERT"))


class TestFreshness(unittest.TestCase):

	def setUp(self):
		self.c = new_oracle()
		as_sender(ALICE, 0)
		queue_ok("torvalds_C")
		self.c.verify_skill("torvalds", "C")

	def test_never_expires_by_default(self):
		self.assertEqual(jload(self.c.get_config())["freshness_window_seconds"], 0)
		clock_at(10 * 365 * 86400)
		self.assertTrue(self.c.is_verified("torvalds", "C", "EXPERT"))

	def test_expires_once_a_window_is_set(self):
		as_sender(OWNER, 0)
		self.c.set_freshness_window(86400)
		clock_at(86401)
		self.assertFalse(self.c.is_verified("torvalds", "C", "EXPERT"))

	def test_inside_the_window_still_passes(self):
		as_sender(OWNER, 0)
		self.c.set_freshness_window(86400)
		clock_at(86399)
		self.assertTrue(self.c.is_verified("torvalds", "C", "EXPERT"))

	def test_stale_flag_is_reported(self):
		as_sender(OWNER, 0)
		self.c.set_freshness_window(3600)
		clock_at(7200)
		self.assertTrue(jload(self.c.get_verification(1))["stale"])
		self.assertFalse(jload(self.c.get_latest("torvalds", "C"))["fresh"])

	def test_setting_the_window_back_to_zero_restores_everything(self):
		as_sender(OWNER, 0)
		self.c.set_freshness_window(3600)
		clock_at(7200)
		self.assertFalse(self.c.is_verified("torvalds", "C", "EXPERT"))
		self.c.set_freshness_window(0)
		self.assertTrue(self.c.is_verified("torvalds", "C", "EXPERT"))


class TestRequireVerified(unittest.TestCase):

	def setUp(self):
		self.c = new_oracle()
		as_sender(ALICE, 0)
		queue_ok("torvalds_C")
		self.c.verify_skill("torvalds", "C")

	def test_passes_and_returns_the_record(self):
		out = jload(self.c.require_verified("torvalds", "C", "PROFICIENT"))
		self.assertTrue(out["ok"])
		self.assertEqual(out["level"], "EXPERT")

	def test_raises_when_the_level_is_too_low(self):
		c = new_oracle()
		as_sender(ALICE, 0)
		queue_ok("octocat_HTML")
		c.verify_skill("octocat", "HTML")
		with self.assertRaises(_UserError) as ctx:
			c.require_verified("octocat", "HTML", "EXPERT")
		self.assertIn("BEGINNER", str(ctx.exception))

	def test_raises_for_an_unknown_pair(self):
		with self.assertRaises(_UserError):
			self.c.require_verified("nobody", "Cobol", "BEGINNER")

	def test_raises_for_a_bad_min_level(self):
		with self.assertRaises(_UserError):
			self.c.require_verified("torvalds", "C", "GURU")

	def test_raises_for_a_stale_record(self):
		as_sender(OWNER, 0)
		self.c.set_freshness_window(3600)
		clock_at(7200)
		with self.assertRaises(_UserError):
			self.c.require_verified("torvalds", "C", "EXPERT")

	def test_it_is_the_raising_twin_of_is_verified(self):
		# The two must never disagree about who passes.
		for pair in (("torvalds", "C"), ("nobody", "Cobol")):
			for level in ("NONE", "BEGINNER", "PROFICIENT", "EXPERT", "GURU"):
				permits = self.c.is_verified(pair[0], pair[1], level)
				try:
					self.c.require_verified(pair[0], pair[1], level)
					raised = False
				except _UserError:
					raised = True
				self.assertEqual(permits, not raised, (pair, level))


class TestListingViews(unittest.TestCase):

	def setUp(self):
		self.c = new_oracle()
		as_sender(OWNER, 0)
		self.c.set_cooldown(0)
		as_sender(ALICE, 0)
		for name, skill in (("torvalds_C", "C"), ("torvalds_Haskell", "Haskell")):
			queue_ok(name)
			self.c.verify_skill("torvalds", skill)
		queue_ok("gvanrossum_Python")
		self.c.verify_skill("gvanrossum", "Python")

	def test_by_user(self):
		out = jload(self.c.get_verifications_by_user("torvalds", 0, 50))
		self.assertEqual(out["total"], 2)
		self.assertEqual(out["returned"], 2)

	def test_by_user_is_newest_first(self):
		out = jload(self.c.get_verifications_by_user("torvalds", 0, 50))
		self.assertEqual([r["verification_id"] for r in out["verifications"]], [2, 1])

	def test_by_user_is_case_insensitive(self):
		self.assertEqual(jload(self.c.get_verifications_by_user("TORVALDS", 0, 50))["total"], 2)

	def test_by_user_unknown_is_empty_not_an_error(self):
		# The DynArray-valued TreeMap answers an EMPTY ARRAY on chain, not None.
		out = jload(self.c.get_verifications_by_user("nobody-at-all", 0, 50))
		self.assertEqual(out["total"], 0)
		self.assertEqual(out["verifications"], [])

	def test_by_skill(self):
		self.assertEqual(jload(self.c.get_verifications_by_skill("C", 0, 50))["total"], 1)
		self.assertEqual(jload(self.c.get_verifications_by_skill("python", 0, 50))["total"], 1)

	def test_by_skill_normalises_whitespace(self):
		c = new_oracle()
		as_sender(ALICE, 0)
		queue_ok("kenil1710_JS")
		c.verify_skill("kenil1710", "Jupyter   Notebook")
		self.assertEqual(jload(c.get_verifications_by_skill("jupyter notebook", 0, 50))["total"], 1)

	def test_by_skill_unknown_is_empty(self):
		self.assertEqual(jload(self.c.get_verifications_by_skill("cobol", 0, 50))["total"], 0)

	def test_paging(self):
		first = jload(self.c.get_verifications_by_user("torvalds", 0, 1))
		second = jload(self.c.get_verifications_by_user("torvalds", 1, 1))
		self.assertEqual(first["verifications"][0]["verification_id"], 2)
		self.assertEqual(second["verifications"][0]["verification_id"], 1)

	def test_limit_is_capped(self):
		out = jload(self.c.get_verifications_by_user("torvalds", 0, 100000))
		self.assertLessEqual(out["returned"], 50)

	def test_junk_paging_arguments_do_not_raise(self):
		for offset in (-5, 0, 10 ** 12, None, "x"):
			for limit in (-5, 0, 10 ** 12, None, "x"):
				jload(self.c.get_verifications_by_user("torvalds", offset, limit))

	def test_get_verification_unknown_id_returns_found_false(self):
		# It must NOT raise. A view that raises reverts every contract that
		# reads it, including payable ones, and takes their callers' value.
		for bad in (0, 999, -1, None, "x", 10 ** 12):
			out = jload(self.c.get_verification(bad))
			self.assertFalse(out["found"], repr(bad))

	def test_get_latest_reports_absence_cleanly(self):
		out = jload(self.c.get_latest("nobody", "cobol"))
		self.assertFalse(out["found"])
		self.assertEqual(out["pending_id"], -1)

	def test_every_view_returns_parseable_json(self):
		for call in (
			lambda: self.c.get_verification(1),
			lambda: self.c.get_verifications_by_user("torvalds", 0, 10),
			lambda: self.c.get_verifications_by_skill("c", 0, 10),
			lambda: self.c.get_stats(),
			lambda: self.c.get_config(),
			lambda: self.c.get_latest("torvalds", "c"),
		):
			self.assertIsInstance(jload(call()), dict)

	def test_summary_shape_is_identical_across_views(self):
		# One shape everywhere, so a field added to _summary cannot go missing
		# from the listing a consumer happens to read.
		direct = set(jload(self.c.get_verification(1)).keys()) - {"found"}
		listed = set(jload(self.c.get_verifications_by_user("torvalds", 0, 50))["verifications"][-1].keys())
		self.assertEqual(direct, listed)


class TestOwnerControls(unittest.TestCase):

	def setUp(self):
		self.c = new_oracle()

	def test_only_owner_can_set_fee(self):
		as_sender(ALICE, 0)
		with self.assertRaises(_UserError):
			self.c.set_fee(GEN)

	def test_only_owner_can_pause(self):
		as_sender(ALICE, 0)
		with self.assertRaises(_UserError):
			self.c.pause()

	def test_only_owner_can_set_windows(self):
		as_sender(ALICE, 0)
		for call in (lambda: self.c.set_cooldown(0), lambda: self.c.set_resolve_window(60),
				lambda: self.c.set_freshness_window(0), lambda: self.c.transfer_ownership(str(BOB)),
				lambda: self.c.withdraw_fees(0)):
			with self.assertRaises(_UserError):
				call()

	def test_fee_ceiling_is_enforced(self):
		as_sender(OWNER, 0)
		with self.assertRaises(_UserError):
			self.c.set_fee(SV.MAX_FEE + 1)
		# Rejected rather than clamped: silently storing 1 while the owner
		# believes 500 is in force is worse than a revert.
		self.assertEqual(int(jload(self.c.get_config())["fee"]), 0)

	def test_negative_fee_refused(self):
		as_sender(OWNER, 0)
		with self.assertRaises(_UserError):
			self.c.set_fee(-1)

	def test_fee_at_the_ceiling_is_allowed(self):
		as_sender(OWNER, 0)
		self.c.set_fee(SV.MAX_FEE)
		self.assertEqual(int(jload(self.c.get_config())["fee"]), SV.MAX_FEE)

	def test_resolve_window_bounds(self):
		as_sender(OWNER, 0)
		for bad in (0, 59, 30 * 86400 + 1, -1):
			with self.assertRaises(_UserError):
				self.c.set_resolve_window(bad)
		self.c.set_resolve_window(60)
		self.c.set_resolve_window(30 * 86400)

	def test_cooldown_bounds(self):
		as_sender(OWNER, 0)
		with self.assertRaises(_UserError):
			self.c.set_cooldown(-1)
		with self.assertRaises(_UserError):
			self.c.set_cooldown(86401)

	def test_freshness_bounds(self):
		as_sender(OWNER, 0)
		with self.assertRaises(_UserError):
			self.c.set_freshness_window(-1)
		with self.assertRaises(_UserError):
			self.c.set_freshness_window(365 * 86400 + 1)

	def test_pause_blocks_new_but_not_reads(self):
		as_sender(ALICE, 0)
		queue_ok("torvalds_C")
		self.c.verify_skill("torvalds", "C")
		as_sender(OWNER, 0)
		self.c.pause()
		self.assertTrue(jload(self.c.get_config())["paused"])
		self.assertTrue(self.c.is_verified("torvalds", "C", "EXPERT"))
		self.assertTrue(jload(self.c.get_verification(1))["found"])
		as_sender(BOB, 0)
		self.assertFalse(jload(self.c.verify_skill("gvanrossum", "Python"))["ok"])

	def test_unpause_restores(self):
		as_sender(OWNER, 0)
		self.c.pause()
		self.c.unpause()
		as_sender(ALICE, 0)
		queue_ok("torvalds_C")
		self.assertTrue(jload(self.c.verify_skill("torvalds", "C"))["ok"])

	def test_ownership_transfer(self):
		as_sender(OWNER, 0)
		self.c.transfer_ownership(str(BOB))
		self.assertEqual(jload(self.c.get_config())["owner"], str(BOB))
		as_sender(OWNER, 0)
		with self.assertRaises(_UserError):
			self.c.pause()
		as_sender(BOB, 0)
		self.c.pause()

	def test_ownership_cannot_go_to_the_zero_address(self):
		as_sender(OWNER, 0)
		with self.assertRaises(_UserError):
			self.c.transfer_ownership("0x" + "0" * 40)

	def test_ownership_rejects_malformed_addresses(self):
		as_sender(OWNER, 0)
		for bad in ("0xabc", "notanaddress", "", "b" * 42, None):
			with self.assertRaises(_UserError):
				self.c.transfer_ownership(bad)

	def test_fee_changes_apply_only_to_new_verifications(self):
		# Every record carries its own fee_snapshot and is unreachable from the
		# setter.
		as_sender(ALICE, 0)
		queue_ok("torvalds_C")
		self.c.verify_skill("torvalds", "C")
		self.assertEqual(int(jload(self.c.get_verification(1))["fee_snapshot"]), 0)
		as_sender(OWNER, 0)
		self.c.set_fee(GEN)
		self.assertEqual(int(jload(self.c.get_verification(1))["fee_snapshot"]), 0)

	def test_resolve_window_changes_apply_only_to_new_verifications(self):
		as_sender(ALICE, 0)
		queue_raw(403, RATE_LIMIT_BODY)
		self.c.verify_skill("torvalds", "C")
		self.assertEqual(jload(self.c.get_verification(1))["resolve_window"], 3600)
		as_sender(OWNER, 0)
		self.c.set_resolve_window(86400)
		self.assertEqual(jload(self.c.get_verification(1))["resolve_window"], 3600)

	def test_withdraw_is_bounded_by_fee_income_not_by_balance(self):
		as_sender(OWNER, 0)
		self.c.set_fee(GEN)
		as_sender(ALICE, GEN)
		queue_ok("torvalds_C")
		self.c.verify_skill("torvalds", "C")
		as_sender(OWNER, 0)
		with self.assertRaises(_UserError):
			self.c.withdraw_fees(2 * GEN)
		before = len(TRANSFERS)
		out = jload(self.c.withdraw_fees(GEN))
		self.assertTrue(out["ok"])
		self.assertEqual(TRANSFERS[before:], [(str(OWNER), GEN)])

	def test_withdraw_cannot_be_repeated(self):
		as_sender(OWNER, 0)
		self.c.set_fee(GEN)
		as_sender(ALICE, GEN)
		queue_ok("torvalds_C")
		self.c.verify_skill("torvalds", "C")
		as_sender(OWNER, 0)
		self.c.withdraw_fees(0)
		with self.assertRaises(_UserError):
			self.c.withdraw_fees(0)

	def test_withdraw_with_no_income_refuses(self):
		as_sender(OWNER, 0)
		with self.assertRaises(_UserError):
			self.c.withdraw_fees(0)

	def test_there_is_no_owner_path_to_user_funds(self):
		# No user funds are ever held: overpayment is returned in the same
		# transaction, so the balance the owner can reach is fee income alone.
		as_sender(OWNER, 0)
		self.c.set_fee(GEN)
		as_sender(ALICE, 5 * GEN)
		queue_ok("torvalds_C")
		self.c.verify_skill("torvalds", "C")
		as_sender(OWNER, 0)
		out = jload(self.c.withdraw_fees(0))
		self.assertEqual(int(out["withdrawn"]), GEN)   # not 5


class TestConsumerAcrossARealBoundary(unittest.TestCase):
	"""SkillConsumer is wired to an ACTUAL SkillVerify, not a fake — because the
	bug being guarded against is precisely that the real oracle might raise
	where a fake would politely return whatever the test author expected. That
	is how an earlier project's consumer shipped a premium-confiscating bug."""

	def setUp(self):
		self.oracle = new_oracle()
		as_sender(OWNER, 0)
		self.oracle.set_cooldown(0)
		as_sender(ALICE, 0)
		queue_ok("gvanrossum_Python")
		self.oracle.verify_skill("gvanrossum", "Python")     # EXPERT
		queue_ok("octocat_HTML")
		self.oracle.verify_skill("octocat", "HTML")          # BEGINNER
		self.consumer = new_consumer(self.oracle)

	def test_check_skill_reads_through_the_oracle(self):
		self.assertTrue(self.consumer.check_skill("gvanrossum", "Python", "EXPERT"))
		self.assertFalse(self.consumer.check_skill("octocat", "HTML", "EXPERT"))
		self.assertTrue(self.consumer.check_skill("octocat", "HTML", "BEGINNER"))

	def test_require_skill_passes(self):
		out = jload(self.consumer.require_skill("gvanrossum", "Python", "PROFICIENT"))
		self.assertTrue(out["ok"])
		self.assertEqual(out["level"], "EXPERT")

	def test_require_skill_reverts_when_unmet(self):
		with self.assertRaises(_UserError) as ctx:
			self.consumer.require_skill("octocat", "HTML", "EXPERT")
		self.assertIn("BEGINNER", str(ctx.exception))

	def test_require_skill_reverts_for_an_unverified_user(self):
		with self.assertRaises(_UserError):
			self.consumer.require_skill("nobody", "Python", "BEGINNER")

	def test_the_two_ladders_agree(self):
		# The consumer keeps its OWN copy of the ladder so the oracle cannot
		# silently redefine what this contract pays for. They must match.
		self.assertEqual(
			jload(self.consumer.get_terms())["levels"],
			jload(self.oracle.get_config())["levels"],
		)

	def test_get_oracle_config_proves_the_wiring(self):
		via = jload(self.consumer.get_oracle_config())
		self.assertEqual(via["owner"], jload(self.oracle.get_config())["owner"])

	# ── the bounty flow ─────────────────────────────────────────────────

	def post(self, skill="Python", level="PROFICIENT", value=GEN, sender=BOB):
		as_sender(sender, value)
		return jload(self.consumer.post_bounty("Port the parser", skill, level))

	def test_post_and_claim(self):
		self.assertTrue(self.post()["ok"])
		as_sender(CAROL, 0)
		before = len(TRANSFERS)
		out = jload(self.consumer.claim_bounty(1, "gvanrossum"))
		self.assertTrue(out["ok"])
		self.assertEqual(int(out["paid"]), GEN)
		self.assertEqual(TRANSFERS[before:], [(str(CAROL), GEN)])

	def test_the_claim_records_the_verification_it_relied_on(self):
		self.post()
		as_sender(CAROL, 0)
		out = jload(self.consumer.claim_bounty(1, "gvanrossum"))
		self.assertEqual(out["verification_id"], 1)
		self.assertNotEqual(out["content_hash"], "")
		self.assertEqual(out["content_hash"], jload(self.oracle.get_verification(1))["content_hash"])

	def test_claim_refused_when_the_level_is_too_low(self):
		self.post(skill="HTML", level="EXPERT")
		as_sender(CAROL, 0)
		before = len(TRANSFERS)
		out = jload(self.consumer.claim_bounty(1, "octocat"))
		self.assertFalse(out["ok"])
		self.assertIn("BEGINNER", out["reason"])
		self.assertEqual(TRANSFERS[before:], [])   # nothing paid out

	def test_claim_refused_for_an_unverified_user(self):
		self.post()
		as_sender(CAROL, 0)
		self.assertFalse(jload(self.consumer.claim_bounty(1, "nobody"))["ok"])

	def test_a_claimed_bounty_cannot_be_claimed_twice(self):
		self.post()
		as_sender(CAROL, 0)
		self.consumer.claim_bounty(1, "gvanrossum")
		before = len(TRANSFERS)
		out = jload(self.consumer.claim_bounty(1, "gvanrossum"))
		self.assertFalse(out["ok"])
		self.assertIn("can never change", out["reason"])
		self.assertEqual(TRANSFERS[before:], [])

	def test_a_claimed_bounty_cannot_be_withdrawn(self):
		self.post()
		as_sender(CAROL, 0)
		self.consumer.claim_bounty(1, "gvanrossum")
		as_sender(BOB, 0)
		before = len(TRANSFERS)
		self.assertFalse(jload(self.consumer.withdraw_bounty(1))["ok"])
		self.assertEqual(TRANSFERS[before:], [])

	def test_only_the_poster_may_withdraw(self):
		self.post(sender=BOB)
		as_sender(CAROL, 0)
		self.assertFalse(jload(self.consumer.withdraw_bounty(1))["ok"])
		as_sender(OWNER, 0)
		self.assertFalse(jload(self.consumer.withdraw_bounty(1))["ok"])
		as_sender(BOB, 0)
		self.assertTrue(jload(self.consumer.withdraw_bounty(1))["ok"])

	def test_the_owner_cannot_reach_a_posters_money(self):
		# The property that makes posting one safe. Enumerated: every write the
		# owner can call is called, and the bounty is compared.
		self.post(sender=BOB)
		before = jload(self.consumer.get_bounty(1))
		as_sender(OWNER, 0)
		self.assertFalse(jload(self.consumer.withdraw_bounty(1))["ok"])
		self.assertFalse(jload(self.consumer.claim_bounty(1, "nobody"))["ok"])
		self.assertEqual(jload(self.consumer.get_bounty(1)), before)

	def test_withdraw_returns_the_full_reward(self):
		self.post(sender=BOB, value=3 * GEN)
		as_sender(BOB, 0)
		before = len(TRANSFERS)
		self.assertTrue(jload(self.consumer.withdraw_bounty(1))["ok"])
		self.assertEqual(TRANSFERS[before:], [(str(BOB), 3 * GEN)])

	def test_open_liability_tracks_exactly(self):
		self.post(value=GEN)
		self.post(value=2 * GEN)
		self.assertEqual(int(jload(self.consumer.get_terms())["open_liability"]), 3 * GEN)
		as_sender(CAROL, 0)
		self.consumer.claim_bounty(1, "gvanrossum")
		self.assertEqual(int(jload(self.consumer.get_terms())["open_liability"]), 2 * GEN)
		as_sender(BOB, 0)
		self.consumer.withdraw_bounty(2)
		self.assertEqual(int(jload(self.consumer.get_terms())["open_liability"]), 0)

	def test_the_books_balance(self):
		self.post(value=GEN)
		self.post(value=2 * GEN)
		as_sender(CAROL, 0)
		self.consumer.claim_bounty(1, "gvanrossum")
		as_sender(BOB, 0)
		self.consumer.withdraw_bounty(2)
		t = jload(self.consumer.get_terms())
		self.assertEqual(
			int(t["total_posted"]),
			int(t["total_paid"]) + int(t["total_withdrawn"]) + int(t["open_liability"]),
		)

	# ── post_bounty is payable and must never revert ────────────────────

	def reject_post(self, title, skill, level, value=GEN):
		as_sender(BOB, value)
		before = len(TRANSFERS)
		out = jload(self.consumer.post_bounty(title, skill, level))
		self.assertFalse(out["ok"], out)
		self.assertEqual(TRANSFERS[before:], [(str(BOB), value)], out["reason"])
		return out

	def test_post_below_the_minimum_refunds(self):
		self.reject_post("t", "Python", "EXPERT", value=1)

	def test_post_above_the_maximum_refunds(self):
		self.reject_post("t", "Python", "EXPERT", value=1000 * GEN)

	def test_post_with_an_empty_title_refunds(self):
		self.reject_post("   ", "Python", "EXPERT")

	def test_post_with_an_empty_skill_refunds(self):
		self.reject_post("t", "  ", "EXPERT")

	def test_post_with_a_bad_level_refunds(self):
		self.reject_post("t", "Python", "GURU")

	def test_post_with_min_level_none_refunds(self):
		# NONE would let anybody claim, verified or not — a bounty that pays
		# everyone is not what its poster meant to fund.
		out = self.reject_post("t", "Python", "NONE")
		self.assertIn("anybody", out["reason"])

	def test_post_never_raises_for_hostile_input(self):
		hostile = ["", " ", "x" * 500, None, {"a": 1}, 7, b"z", "\x00"]
		for title in hostile:
			for skill in hostile:
				for level in hostile + ["EXPERT"]:
					as_sender(BOB, GEN)
					try:
						out = jload(self.consumer.post_bounty(title, skill, level))
					except Exception as exc:
						self.fail("post_bounty raised for %r/%r/%r: %r" % (title, skill, level, exc))
					if not out["ok"]:
						self.assertEqual(int(out["refunded"]), GEN)

	# ── THE LESSON THIS FILE EXISTS TO ENCODE ───────────────────────────

	def test_an_exploding_oracle_cannot_confiscate_a_claim(self):
		"""A cross-contract view that raises propagates the raise across the
		boundary and reverts the caller. Every oracle read goes through
		_level_of, which wraps it, so the claim is REFUSED rather than
		reverting with the bounty's money inside the contract."""
		self.post()
		ORACLE["raise_on"] = "get_latest"
		as_sender(CAROL, 0)
		before = len(TRANSFERS)
		out = jload(self.consumer.claim_bounty(1, "gvanrossum"))
		self.assertFalse(out["ok"])
		self.assertIn("oracle unreachable", out["reason"])
		self.assertEqual(TRANSFERS[before:], [])
		# And the bounty is untouched, so it can still be claimed later.
		self.assertEqual(jload(self.consumer.get_bounty(1))["status"], "OPEN")

	def test_an_exploding_oracle_cannot_confiscate_a_post(self):
		ORACLE["raise_on"] = "get_latest"
		as_sender(BOB, GEN)
		out = jload(self.consumer.post_bounty("t", "Python", "EXPERT"))
		self.assertTrue(out["ok"])   # posting never reads the oracle at all

	def test_check_skill_is_false_when_the_oracle_explodes(self):
		ORACLE["raise_on"] = "get_latest"
		self.assertFalse(self.consumer.check_skill("gvanrossum", "Python", "BEGINNER"))

	def test_require_skill_reverts_when_the_oracle_explodes(self):
		ORACLE["raise_on"] = "get_latest"
		with self.assertRaises(_UserError):
			self.consumer.require_skill("gvanrossum", "Python", "BEGINNER")

	def test_get_skill_report_explains_an_unreachable_oracle(self):
		ORACLE["raise_on"] = "get_latest"
		out = jload(self.consumer.get_skill_report("gvanrossum", "Python"))
		self.assertFalse(out["found"])
		self.assertIn("unreachable", out["reason"])

	def test_a_claim_after_a_stale_verification_is_refused(self):
		self.post()
		as_sender(OWNER, 0)
		self.oracle.set_freshness_window(3600)
		clock_at(7200)
		as_sender(CAROL, 0)
		before = len(TRANSFERS)
		out = jload(self.consumer.claim_bounty(1, "gvanrossum"))
		self.assertFalse(out["ok"])
		self.assertIn("stale", out["reason"])
		self.assertEqual(TRANSFERS[before:], [])

	def test_consumer_views_never_raise_on_junk(self):
		for bad in (0, -1, 999, None, "x"):
			self.assertFalse(jload(self.consumer.get_bounty(bad))["found"])
			self.assertFalse(jload(self.consumer.claim_bounty(bad, "gvanrossum"))["ok"])
			self.assertFalse(jload(self.consumer.withdraw_bounty(bad))["ok"])

	def test_bounty_listing_views(self):
		self.post(skill="Python")
		self.post(skill="HTML", level="BEGINNER")
		self.assertEqual(jload(self.consumer.get_bounties(0, 50))["total"], 2)
		self.assertEqual(jload(self.consumer.get_bounties_by_skill("python", 0, 50))["total"], 1)
		self.assertEqual(jload(self.consumer.get_bounties_by_skill("cobol", 0, 50))["total"], 0)


class TestConsensusShape(unittest.TestCase):
	"""What happens when validators DISAGREE. On chain the transaction lands
	UNDETERMINED and applies NOTHING; the stub raises so a test cannot mistake a
	broken round for a working one."""

	def setUp(self):
		self.c = new_oracle()

	def test_agreement_commits(self):
		as_sender(ALICE, 0)
		queue_ok("torvalds_C")
		self.c.verify_skill("torvalds", "C")
		self.assertTrue(LAST_CONSENSUS["agreed"])

	def test_a_different_level_from_the_validator_is_a_disagreement(self):
		as_sender(ALICE, 0)
		FETCH_QUEUE.append((200, fixture_body("torvalds_C")))          # leader: EXPERT
		VALIDATOR_QUEUE.append([(200, fixture_body("torvalds_Haskell"))])  # validator: NONE
		with self.assertRaises(AssertionError):
			self.c.verify_skill("torvalds", "C")

	def test_an_undetermined_round_applies_nothing(self):
		before = jload(self.c.get_stats())
		as_sender(ALICE, 0)
		FETCH_QUEUE.append((200, fixture_body("torvalds_C")))
		VALIDATOR_QUEUE.append([(200, fixture_body("torvalds_Haskell"))])
		try:
			self.c.verify_skill("torvalds", "C")
		except AssertionError:
			pass
		# On chain nothing is applied; the stub cannot roll back, so what is
		# asserted is that the disagreement was DETECTED rather than swallowed.
		self.assertFalse(LAST_CONSENSUS["agreed"])
		self.assertEqual(before["resolved"], 0)

	def test_byte_differences_are_a_disagreement_now_that_the_counts_are_bound(self):
		# THE PRICE OF BINDING THE COUNTS, asserted so it is a decision rather
		# than a surprise. A repository pushed between the leader's fetch and a
		# validator's changes `size`, and the round now lands UNDETERMINED
		# where it used to commit.
		#
		# It is the right trade. UNDETERMINED is a retry that costs a caller
		# nothing — verify_skill writes no storage on an undetermined round —
		# and the alternative, leaving the counts uncompared, is what let a
		# leader forge the numbers the level is computed from. A retry is
		# recoverable; a forged EXPERT on chain is not.
		leader = json.loads(fixture_body("torvalds_C"))
		validator = json.loads(fixture_body("torvalds_C"))
		validator["items"][0]["size"] += 17          # somebody pushed
		validator["total_count"] = 8
		as_sender(ALICE, 0)
		FETCH_QUEUE.append((200, json.dumps(leader)))
		VALIDATOR_QUEUE.append([(200, json.dumps(validator))])
		with self.assertRaises(AssertionError):
			self.c.verify_skill("torvalds", "C")
		self.assertFalse(LAST_CONSENSUS["agreed"])

	def test_the_same_bytes_on_both_nodes_still_agree(self):
		# The other half of the trade: an unchanged repository list commits,
		# which is the ordinary case and must not have become fragile.
		body = fixture_body("torvalds_C")
		as_sender(ALICE, 0)
		FETCH_QUEUE.append((200, body))
		VALIDATOR_QUEUE.append([(200, body)])
		out = jload(self.c.verify_skill("torvalds", "C"))
		self.assertTrue(out["ok"])
		self.assertTrue(LAST_CONSENSUS["agreed"])

	def test_both_nodes_rate_limited_agree_on_unavailable(self):
		as_sender(ALICE, 0)
		FETCH_QUEUE.append((403, RATE_LIMIT_BODY))
		VALIDATOR_QUEUE.append([(403, RATE_LIMIT_BODY)])
		out = jload(self.c.verify_skill("torvalds", "C"))
		self.assertEqual(out["status"], "PENDING")
		self.assertTrue(LAST_CONSENSUS["agreed"])

	def test_one_node_rate_limited_is_a_disagreement(self):
		# Correct: the leader has an answer the validator cannot check. The
		# round is spent rather than a guess being recorded.
		as_sender(ALICE, 0)
		FETCH_QUEUE.append((200, fixture_body("torvalds_C")))
		VALIDATOR_QUEUE.append([(403, RATE_LIMIT_BODY)])
		with self.assertRaises(AssertionError):
			self.c.verify_skill("torvalds", "C")

	def test_a_500_and_a_403_still_agree_because_both_are_unavailable(self):
		as_sender(ALICE, 0)
		FETCH_QUEUE.append((503, "down"))
		VALIDATOR_QUEUE.append([(403, RATE_LIMIT_BODY)])
		out = jload(self.c.verify_skill("torvalds", "C"))
		self.assertEqual(out["status"], "PENDING")


class TestConsensusBindsTheCountsToTheLevel(unittest.TestCase):
	"""THE REJECTION THIS FILE EXISTS TO KEEP CLOSED.

	The level stored on a record used to be derived from `repo_count` and
	`total_bytes` that nothing compared: validators voted on one string, and
	the two numbers that decide what that string MEANS rode along unchecked.
	A leader could therefore answer NONE — which validators looking at a real
	NONE would unanimously agree with — while attaching repo_count=100 and
	total_bytes=10**9, and the contract would compute EXPERT from the forged
	numbers and store it as a consensus result.

	Two independent gates close it, and both are tested here:

	  1. CONSENSUS. The compared key is level + repo_count + total_bytes
	     (_compare_key), so the numbers are agreed, not merely carried.
	  2. COHERENCE. _apply re-runs the ladder over the agreed counts and
	     refuses an axis its own counts contradict — which catches a payload
	     that got past gate 1 with matching counts and a wrong level.

	The forgery is staged with LEADER_FORGE, which tampers with the leader's
	payload after it is computed and before anyone sees it. That is precisely
	the power a real leader has, and nothing weaker reproduces the bug."""

	def setUp(self):
		self.c = new_oracle()

	# ── gate 1: the counts are part of what consensus compares ─────────────

	def test_the_compared_key_binds_the_counts(self):
		base = {"axis": "NONE", "repo_count": 0, "total_bytes": 0}
		forged = {"axis": "NONE", "repo_count": 100, "total_bytes": 10 ** 9}
		self.assertNotEqual(SV._compare_key(base), SV._compare_key(forged))
		# ...where the old comparison saw one value and agreed.
		self.assertEqual(SV._axis_of(base), SV._axis_of(forged))

	def test_the_compared_key_cannot_collide_across_the_separator(self):
		# ("1", "23") and ("12", "3") must not fold into one key.
		a = {"axis": "NONE", "repo_count": 1, "total_bytes": 23}
		b = {"axis": "NONE", "repo_count": 12, "total_bytes": 3}
		self.assertNotEqual(SV._compare_key(a), SV._compare_key(b))

	def test_a_missing_count_is_not_zero(self):
		# A validator that legitimately measured ZERO repositories must not be
		# made to agree with a payload that omitted the field.
		self.assertNotEqual(
			SV._compare_key({"axis": "NONE", "repo_count": 0, "total_bytes": 0}),
			SV._compare_key({"axis": "NONE"}),
		)

	def test_the_non_level_axes_still_compare_bare(self):
		# NO_SUCH_USER and UNAVAILABLE carry no counts — binding them would
		# make two rate-limited nodes disagree for no reason (rule 4).
		self.assertEqual(SV._compare_key({"axis": "UNAVAILABLE", "status": 403}),
			SV._compare_key({"axis": "UNAVAILABLE", "status": 503}))
		self.assertEqual(SV._compare_key({"axis": "NO_SUCH_USER", "status": 422}),
			SV._compare_key({"axis": "NO_SUCH_USER", "status": 422}))

	def test_compare_key_never_raises(self):
		for junk in (None, 0, "", b"x", [], {}, {"axis": None},
				{"axis": "EXPERT", "repo_count": "many", "total_bytes": None},
				{"axis": "EXPERT", "repo_count": [1], "total_bytes": {"a": 1}}):
			self.assertIsInstance(SV._compare_key(junk), str)

	def test_leader_sends_NONE_axis_but_forges_repo_count_100(self):
		# THE EXACT REJECTION. Validators see a real NONE and vote NONE; the
		# leader broadcasts NONE with 100 repositories and a gigabyte, from
		# which the old code computed and stored EXPERT.
		body = fixture_body("torvalds_Haskell")            # a genuine NONE
		as_sender(ALICE, 0)
		FETCH_QUEUE.append((200, body))
		VALIDATOR_QUEUE.append([(200, body)])

		def forge(result):
			result["repo_count"] = 100
			result["total_bytes"] = 10 ** 9
			return result

		LEADER_FORGE.append(forge)
		with self.assertRaises(AssertionError):
			self.c.verify_skill("torvalds", "Haskell")
		self.assertFalse(LAST_CONSENSUS["agreed"])
		# Nothing was stored, and the forged EXPERT exists nowhere.
		self.assertEqual(jload(self.c.get_stats())["resolved"], 0)
		self.assertFalse(self.c.is_verified("torvalds", "Haskell", "EXPERT"))

	def test_leader_sends_EXPERT_axis_but_forges_repo_count_0(self):
		# The mirror: a real EXPERT downgraded by forged counts. Under the old
		# code the record landed NONE — a leader could silently deny a genuine
		# expert, which is the same hole pointing the other way.
		body = fixture_body("torvalds_C")                  # a genuine EXPERT
		as_sender(ALICE, 0)
		FETCH_QUEUE.append((200, body))
		VALIDATOR_QUEUE.append([(200, body)])

		def forge(result):
			result["repo_count"] = 0
			result["total_bytes"] = 0
			return result

		LEADER_FORGE.append(forge)
		with self.assertRaises(AssertionError):
			self.c.verify_skill("torvalds", "C")
		self.assertFalse(LAST_CONSENSUS["agreed"])
		self.assertEqual(jload(self.c.get_stats())["resolved"], 0)

	def test_validators_disagreeing_on_repo_count_alone_is_undetermined(self):
		# Same level on both nodes, different repository counts. Before the
		# fix this committed; the level was the only thing compared.
		leader = json.loads(fixture_body("torvalds_C"))
		validator = json.loads(fixture_body("torvalds_C"))
		# Drop one matching repository from the validator's view. Eight C
		# repositories become seven — still EXPERT, a different repo_count.
		drop = next(i for i, it in enumerate(validator["items"])
			if SV._normalize_skill(it.get("language")) == "c")
		validator["items"].pop(drop)
		as_sender(ALICE, 0)
		FETCH_QUEUE.append((200, json.dumps(leader)))
		VALIDATOR_QUEUE.append([(200, json.dumps(validator))])
		# Both nodes still score EXPERT — the LEVEL agrees.
		self.assertEqual(SV._score(leader, "C")["level"], "EXPERT")
		self.assertEqual(SV._score(validator, "C")["level"], "EXPERT")
		self.assertNotEqual(SV._score(leader, "C")["repo_count"],
			SV._score(validator, "C")["repo_count"])
		with self.assertRaises(AssertionError):
			self.c.verify_skill("torvalds", "C")
		self.assertFalse(LAST_CONSENSUS["agreed"])

	def test_validators_disagreeing_on_total_bytes_alone_is_undetermined(self):
		leader = json.loads(fixture_body("torvalds_C"))
		validator = json.loads(fixture_body("torvalds_C"))
		for item in validator["items"]:
			if SV._normalize_skill(item.get("language")) == "c":
				item["size"] = int(item.get("size", 0)) + 1000
		as_sender(ALICE, 0)
		FETCH_QUEUE.append((200, json.dumps(leader)))
		VALIDATOR_QUEUE.append([(200, json.dumps(validator))])
		self.assertEqual(SV._score(leader, "C")["repo_count"],
			SV._score(validator, "C")["repo_count"])
		with self.assertRaises(AssertionError):
			self.c.verify_skill("torvalds", "C")
		self.assertFalse(LAST_CONSENSUS["agreed"])

	def test_matching_axis_and_matching_counts_are_accepted(self):
		# The whole point: an honest round still commits, and it commits the
		# numbers both nodes saw.
		as_sender(ALICE, 0)
		queue_ok("torvalds_C")
		out = jload(self.c.verify_skill("torvalds", "C"))
		self.assertTrue(out["ok"])
		self.assertTrue(LAST_CONSENSUS["agreed"])
		self.assertEqual(out["status"], "RESOLVED")
		self.assertEqual(out["level"], "EXPERT")
		truth = SV._score(fixture_doc("torvalds_C"), "C")
		self.assertEqual(out["repo_count"], truth["repo_count"])
		self.assertEqual(int(out["total_bytes"]), truth["total_bytes"])

	# ── gate 2: the coherence check inside _apply ──────────────────────────
	#
	# Reached directly, because gate 1 stops these payloads before _apply ever
	# sees them. That is the point of having two gates, and a test that could
	# only exercise the first would leave the second unproven.

	_pending_seq = 0

	def _pending_record(self, skill="Go"):
		"""A PENDING record to hand a forged outcome to.

		A fresh username every call: the cooldown and the in-flight guard are
		both doing their jobs, and reusing one pair would have this helper
		testing those instead of the coherence gate."""
		as_sender(OWNER, 0)
		self.c.set_cooldown(0)
		TestConsensusBindsTheCountsToTheLevel._pending_seq += 1
		user = "forge-subject-%d" % TestConsensusBindsTheCountsToTheLevel._pending_seq
		as_sender(ALICE, 0)
		queue_raw(403, RATE_LIMIT_BODY)
		out = jload(self.c.verify_skill(user, skill))
		self.assertTrue(out["ok"], out.get("reason"))
		self.assertEqual(out["status"], "PENDING")
		return self.c.verifications.get(out["verification_id"])

	def test_apply_refuses_NONE_carrying_expert_sized_counts(self):
		record = self._pending_record()
		applied = self.c._apply(record, {
			"axis": "NONE", "status": 200, "repo_count": 100,
			"total_bytes": 10 ** 9, "index_count": 100, "top_repos": [], "reason": "",
		})
		self.assertFalse(applied["resolved"])
		self.assertTrue(applied.get("incoherent"))
		self.assertEqual(str(record.status), "PENDING")
		self.assertEqual(str(record.level), "")
		self.assertEqual(int(record.repo_count), 0)
		self.assertEqual(int(record.total_bytes), 0)
		self.assertIn("incoherent", str(record.last_reason))

	def test_apply_refuses_EXPERT_carrying_zero_counts(self):
		record = self._pending_record()
		applied = self.c._apply(record, {
			"axis": "EXPERT", "status": 200, "repo_count": 0,
			"total_bytes": 0, "index_count": 0, "top_repos": [], "reason": "",
		})
		self.assertFalse(applied["resolved"])
		self.assertTrue(applied.get("incoherent"))
		self.assertEqual(str(record.status), "PENDING")
		self.assertEqual(str(record.level), "")

	def test_apply_refuses_every_level_paired_with_the_wrong_counts(self):
		# Exhaustive over the ladder: for each level, counts that produce a
		# DIFFERENT level must be refused, and only the matching pair stored.
		counts = {
			"NONE": (0, 0),
			"BEGINNER": (1, 10),
			"PROFICIENT": (3, 500),
			"EXPERT": (5, 1000),
		}
		for claimed in ("NONE", "BEGINNER", "PROFICIENT", "EXPERT"):
			for source, (repos, size) in counts.items():
				record = self._pending_record()
				applied = self.c._apply(record, {
					"axis": claimed, "status": 200, "repo_count": repos,
					"total_bytes": size, "index_count": repos,
					"top_repos": [], "reason": "",
				})
				label = "%s claimed over %s counts" % (claimed, source)
				if claimed == source:
					self.assertTrue(applied["resolved"], label)
					self.assertEqual(str(record.level), claimed, label)
					self.assertEqual(int(record.repo_count), repos, label)
					self.assertEqual(int(record.total_bytes), size, label)
				else:
					self.assertFalse(applied["resolved"], label)
					self.assertTrue(applied.get("incoherent"), label)
					self.assertEqual(str(record.level), "", label)

	def test_an_incoherent_payload_leaves_the_record_resolvable(self):
		# It must be a RETRY, not a grave. The record stays PENDING, keeps its
		# in-flight slot, and the next honest round settles it.
		record = self._pending_record()
		before = int(record.attempts)
		self.c._apply(record, {
			"axis": "EXPERT", "status": 200, "repo_count": 0,
			"total_bytes": 0, "index_count": 0, "top_repos": [], "reason": "",
		})
		self.assertEqual(int(record.attempts), before + 1)
		self.assertTrue(self.c._mutable(record))
		# resolve_pending re-runs against the record's OWN username and skill,
		# so the honest answer has to be a Go document.
		honest = {"total_count": 5, "items": [
			{"name": "r%d" % i, "language": "Go", "size": 400} for i in range(5)]}
		as_sender(BOB, 0)
		queue_raw(200, json.dumps(honest))
		out = jload(self.c.resolve_pending(int(record.verification_id)))
		self.assertTrue(out["ok"])
		self.assertEqual(out["status"], "RESOLVED")
		self.assertEqual(out["level"], "EXPERT")

	def test_an_incoherent_payload_never_raises(self):
		# Rule 1. This path is reachable from a payable method.
		record = self._pending_record()
		for junk_repos, junk_bytes in ((10 ** 40, 10 ** 40), (-5, -5), ("x", None)):
			applied = self.c._apply(record, {
				"axis": "EXPERT", "status": 200, "repo_count": junk_repos,
				"total_bytes": junk_bytes, "index_count": 0,
				"top_repos": [], "reason": "",
			})
			self.assertIn("resolved", applied)

	def test_a_coherent_payload_stores_the_agreed_values_verbatim(self):
		# Rule 3 of the fix: what lands is what was agreed, not a
		# recomputation that happens to coincide with it.
		record = self._pending_record()
		applied = self.c._apply(record, {
			"axis": "PROFICIENT", "status": 200, "repo_count": 4,
			"total_bytes": 777, "index_count": 9,
			"top_repos": ["a", "b"], "reason": "",
		})
		self.assertTrue(applied["resolved"])
		self.assertEqual(str(record.level), "PROFICIENT")
		self.assertEqual(int(record.repo_count), 4)
		self.assertEqual(int(record.total_bytes), 777)
		self.assertEqual(str(record.content_hash), SV._content_hash(
			str(record.github_username), str(record.skill), "PROFICIENT", 4, 777))

	def test_no_such_user_is_unaffected_by_the_coherence_gate(self):
		# NO_SUCH_USER stores level NONE with zero counts, which the ladder
		# agrees with — the gate must not turn a 422 into a PENDING loop.
		as_sender(ALICE, 0)
		queue_raw(422, '{"message":"Validation Failed"}')
		out = jload(self.c.verify_skill("ghost-user", "Go"))
		self.assertEqual(out["status"], "RESOLVED")
		self.assertEqual(out["level"], "NONE")
		self.assertFalse(out["user_found"])


class TestStoredFieldsAreRecomputed(unittest.TestCase):
	"""Every stored field is derived from the agreed evidence rather than copied
	from wherever it was convenient — so a record whose hash does not match its
	own fields is impossible to produce."""

	def setUp(self):
		self.c = new_oracle()

	def test_level_is_recomputed_from_the_counts(self):
		# A leader whose reported level contradicts its own counts must not be
		# able to store the level it claimed.
		as_sender(ALICE, 0)
		doc = {"total_count": 1, "items": [{"name": "a", "language": "Go", "size": 1}]}
		FETCH_QUEUE.append((200, json.dumps(doc)))
		VALIDATOR_QUEUE.append([(200, json.dumps(doc))])
		out = jload(self.c.verify_skill("someone", "Go"))
		self.assertEqual(out["level"], "BEGINNER")
		self.assertEqual(out["level"], SV._level_for(out["repo_count"], int(out["total_bytes"])))

	def test_hash_matches_the_stored_fields_for_every_level(self):
		as_sender(OWNER, 0)
		self.c.set_cooldown(0)
		cases = [
			("torvalds_C", "C", "EXPERT"),
			("octocat_HTML", "HTML", "BEGINNER"),
			("torvalds_Haskell", "Haskell", "NONE"),
			("gvanrossum_Python", "Python", "EXPERT"),
		]
		for i, (fixture, skill, expected) in enumerate(cases):
			as_sender(ALICE, 0)
			queue_ok(fixture)
			out = jload(self.c.verify_skill("user%d" % i, skill))
			self.assertEqual(out["level"], expected, fixture)
			row = jload(self.c.get_verification(out["verification_id"]))
			self.assertEqual(
				row["content_hash"],
				SV._content_hash(row["github_username"], row["skill"], row["level"],
					row["repo_count"], int(row["total_bytes"])),
				fixture,
			)

	def test_top_repos_round_trip_through_storage_exactly(self):
		as_sender(ALICE, 0)
		queue_ok("torvalds_C")
		self.c.verify_skill("torvalds", "C")
		expected = SV._score(fixture_doc("torvalds_C"), "C")["top_repos"]
		self.assertEqual(jload(self.c.get_verification(1))["top_repos"], expected)

	def test_top_list_is_defensive(self):
		self.assertEqual(SV._top_list(""), [])
		self.assertEqual(SV._top_list(None), [])
		self.assertEqual(SV._top_list("not json"), [])
		self.assertEqual(SV._top_list('{"a":1}'), [])
		self.assertEqual(SV._top_list('["a","b","c","d","e"]'), ["a", "b", "c"])

	def test_count_of_is_defensive(self):
		self.assertEqual(SV._count_of(None), 0)
		self.assertEqual(SV._count_of([]), 0)
		self.assertEqual(SV._count_of([1, 2]), 2)
		self.assertEqual(SV._count_of(5), 0)


class TestHelperFuzz(unittest.TestCase):
	"""NONE OF THE PURE HELPERS MAY RAISE, FOR ANY INPUT. verify_skill is
	payable, and a helper that raises on a malformed argument is rule 1's
	fund-loss bug arriving through the front door."""

	HOSTILE = [None, "", " ", "\x00", "\n\t", "a" * 5000, {"a": 1}, [1, 2], 0, -1,
		10 ** 40, True, False, b"bytes", 3.5, (), set()]

	def test_no_helper_raises(self):
		helpers = [
			("_as_int", lambda v: SV._as_int(v, 0)),
			("_as_text", SV._as_text),
			("_normalize_username", SV._normalize_username),
			("_normalize_skill", SV._normalize_skill),
			("_display_skill", SV._display_skill),
			("_username_problem", SV._username_problem),
			("_skill_problem", SV._skill_problem),
			("_pct", SV._pct),
			("_rank", SV._rank),
			("_fnv", SV._fnv),
			("_top_list", SV._top_list),
			("_count_of", SV._count_of),
			("_axis_of", SV._axis_of),
			("_epoch_from_iso", SV._epoch_from_iso),
		]
		for name, fn in helpers:
			for value in self.HOSTILE:
				try:
					fn(value)
				except Exception as exc:
					self.fail("%s raised for %r: %r" % (name, value, exc))

	def test_two_argument_helpers_do_not_raise(self):
		for a in self.HOSTILE:
			for b in self.HOSTILE:
				try:
					SV._level_for(a, b)
					SV._search_url(SV._as_text(a), SV._as_text(b))
					SV._score(a, SV._as_text(b))
				except Exception as exc:
					self.fail("raised for (%r, %r): %r" % (a, b, exc))

	def test_content_hash_does_not_raise(self):
		for v in self.HOSTILE:
			try:
				SV._content_hash(v, v, v, v, v)
			except Exception as exc:
				self.fail("_content_hash raised for %r: %r" % (v, exc))

	def test_consumer_helpers_do_not_raise(self):
		for name, fn in (("_as_text", SC._as_text), ("_normalize_username", SC._normalize_username),
				("_normalize_skill", SC._normalize_skill), ("_rank", SC._rank), ("_as_json", SC._as_json)):
			for value in self.HOSTILE:
				try:
					fn(value)
				except Exception as exc:
					self.fail("consumer %s raised for %r: %r" % (name, value, exc))

	def test_clamp_is_total(self):
		for v in (-10 ** 40, -1, 0, 1, 10 ** 40):
			self.assertGreaterEqual(SV._clamp(v, 0, 100), 0)
			self.assertLessEqual(SV._clamp(v, 0, 100), 100)

	def test_as_int_rejects_bools(self):
		# isinstance(True, int) is True in Python. A JSON `true` must not become
		# the number 1 anywhere a count or a size is read.
		self.assertEqual(SV._as_int(True, 42), 42)
		self.assertEqual(SV._as_int(False, 42), 42)

	def test_epoch_parser(self):
		self.assertEqual(SV._epoch_from_iso("1970-01-01T00:00:00Z"), 0)
		self.assertEqual(SV._epoch_from_iso("1970-01-02T00:00:00Z"), 86400)
		self.assertEqual(SV._epoch_from_iso("2026-09-07T12:00:00Z") % 86400, 43200)
		for junk in ("", "x", "2026-13-01T00:00:00Z", "2026-01-32T00:00:00Z",
				"2026-01-01T25:00:00Z", "2026-01-01T00:61:00Z", None, 5):
			self.assertEqual(SV._epoch_from_iso(junk), 0, repr(junk))

	def test_a_zero_clock_does_not_break_the_cooldown(self):
		# _now() returns 0 when the block carries no parseable datetime. The
		# cooldown must not then lock every wallet out forever.
		c = new_oracle()
		set_clock("")
		as_sender(ALICE, 0)
		queue_ok("torvalds_C")
		self.assertTrue(jload(c.verify_skill("torvalds", "C"))["ok"])
		queue_ok("gvanrossum_Python")
		self.assertTrue(jload(c.verify_skill("gvanrossum", "Python"))["ok"])


class TestArtifact(unittest.TestCase):
	"""THE ARTIFACT IS WHAT GETS DEPLOYED, so "the source is correct" is only
	half a claim.

	The whole battery is re-run through `build/SkillVerify.min.py` — the
	identifier-mangled bytes — using the name map to reach the renamed helpers.
	This is not paranoia. A previous project's first working mangle renamed a
	parameter to a name a local already held, every market was validated with
	its own question as its aggregator, and it parsed, linted, validated and
	would have deployed."""

	@classmethod
	def setUpClass(cls):
		cls.available = ARTIFACT.exists() and CONSUMER_ARTIFACT.exists()
		if not cls.available:
			return
		cls.map = json.loads((ROOT / "build" / "SkillVerify.names.json").read_text())
		cls.cmap = json.loads((ROOT / "build" / "SkillConsumer.names.json").read_text())
		cls.mod = load_full(ARTIFACT, "sv_min")
		cls.cmod = load_full(CONSUMER_ARTIFACT, "sc_min")

	def setUp(self):
		if not self.available:
			self.skipTest("run tools/build.sh first")

	def name(self, original):
		return self.map.get(original, original)

	def fn(self, original):
		return getattr(self.mod, self.name(original))

	# ── the ceiling that decides whether this ships at all ───────────────

	def test_artifact_within_the_measured_bradbury_budget(self):
		self.assertLess(len(ARTIFACT.read_bytes()), ARTIFACT_BUDGET)
		self.assertLess(len(CONSUMER_ARTIFACT.read_bytes()), ARTIFACT_BUDGET)

	def test_artifact_keeps_the_runner_pin_byte_for_byte(self):
		self.assertEqual(
			ARTIFACT.read_text(encoding="utf8").splitlines()[0],
			SOURCE.read_text(encoding="utf8").splitlines()[0],
		)

	# ── the mangle must be a rename and nothing else ────────────────────

	def test_public_abi_is_untouched(self):
		# Public method names ARE the ABI — the deploy script, the E2E suite and
		# every cross-contract caller address them by name.
		for method in ("verify_skill", "resolve_pending", "settle_stalled",
				"get_verification", "get_verifications_by_user",
				"get_verifications_by_skill", "is_verified", "require_verified",
				"get_stats", "get_config", "get_latest", "set_fee", "pause",
				"unpause", "transfer_ownership", "withdraw_fees",
				"set_cooldown", "set_resolve_window", "set_freshness_window"):
			self.assertTrue(hasattr(self.mod.SkillVerify, method), method)
			self.assertNotIn(method, self.map, method + " was renamed — that is the ABI")

	def test_consumer_public_abi_is_untouched(self):
		for method in ("require_skill", "check_skill", "get_skill_report",
				"post_bounty", "claim_bounty", "withdraw_bounty", "get_bounty",
				"get_bounties", "get_bounties_by_skill", "get_terms",
				"get_oracle_config"):
			self.assertTrue(hasattr(self.cmod.SkillConsumer, method), method)
			self.assertNotIn(method, self.cmap, method)

	def test_class_names_survive(self):
		self.assertTrue(hasattr(self.mod, "SkillVerify"))
		self.assertTrue(hasattr(self.cmod, "SkillConsumer"))

	def test_no_replacement_shadows_an_existing_name(self):
		"""THE REGRESSION FOR THE BUG THAT NEARLY SHIPPED. A replacement name
		may never be a name that already appears anywhere in the pre-mangle
		text, or it silently merges two bindings."""
		for label, mapping, pre in (
			("oracle", self.map, ROOT / "build" / "SkillVerify.premangle.py"),
			("consumer", self.cmap, ROOT / "build" / "SkillConsumer.premangle.py"),
		):
			text = pre.read_text(encoding="utf8")
			existing = {n.id for n in ast.walk(ast.parse(text)) if isinstance(n, ast.Name)}
			existing |= {n.name for n in ast.walk(ast.parse(text)) if isinstance(n, ast.FunctionDef)}
			existing |= {n.attr for n in ast.walk(ast.parse(text)) if isinstance(n, ast.Attribute)}
			for original, replacement in mapping.items():
				self.assertNotIn(replacement, existing,
					"%s: %s -> %s collides with an existing name" % (label, original, replacement))

	def test_the_mapping_is_injective(self):
		# Two originals mapping to one replacement merges two bindings, which is
		# the same failure by another route.
		for label, mapping in (("oracle", self.map), ("consumer", self.cmap)):
			self.assertEqual(len(set(mapping.values())), len(mapping), label)

	def test_no_string_literal_was_renamed(self):
		# The JSON keys the views return ARE the API. If a literal moved, a
		# consumer reading `level` would get nothing.
		src_strings = {n.value for n in ast.walk(ast.parse(SOURCE.read_text(encoding="utf8")))
			if isinstance(n, ast.Constant) and isinstance(n.value, str)}
		art_strings = {n.value for n in ast.walk(ast.parse(ARTIFACT.read_text(encoding="utf8")))
			if isinstance(n, ast.Constant) and isinstance(n.value, str)}
		for required in ("EXPERT", "PROFICIENT", "BEGINNER", "NONE", "PENDING",
				"RESOLVED", "STALLED", "UNAVAILABLE", "NO_SUCH_USER",
				"github_repo_size_kb", "verification_id", "content_hash", "level"):
			self.assertIn(required, src_strings, required)
			self.assertIn(required, art_strings, required + " lost in the mangle")

	# ── behaviour, through the mangled bytes ────────────────────────────

	def test_the_ladder_is_identical(self):
		level_for = self.fn("_level_for")
		for repos in range(0, 12):
			for size in (0, 1, 499, 500, 999, 1000, 10 ** 9):
				self.assertEqual(level_for(repos, size), SV._level_for(repos, size))

	def test_the_url_builder_is_identical(self):
		search_url = self.fn("_search_url")
		for user, skill in (("torvalds", "C"), ("nlohmann", "C++"), ("microsoft", "C#"),
				("jakevdp", "Jupyter Notebook"), ("kenil1710", "TypeScript")):
			self.assertEqual(search_url(user, skill), SV._search_url(user, skill))

	def test_percent_encoding_is_identical(self):
		pct = self.fn("_pct")
		for value in ("c++", "c#", "jupyter notebook", "objective-c", "a&b", '"'):
			self.assertEqual(pct(value), SV._pct(value))

	def test_scoring_is_identical_on_every_fixture(self):
		score = self.fn("_score")
		for name, skill in (("torvalds_C", "C"), ("gvanrossum_Python", "Python"),
				("kenil1710_JS", "JavaScript"), ("torvalds_Haskell", "Haskell"),
				("octocat_HTML", "HTML"), ("nlohmann_Cpp", "C++")):
			self.assertEqual(score(fixture_doc(name), skill), SV._score(fixture_doc(name), skill), name)

	def test_the_unrecognised_language_bug_is_still_closed_in_the_artifact(self):
		# The one assertion that must survive every transform.
		score = self.fn("_score")
		out = score(fixture_doc("torvalds_bogus"), "Notalanguage")
		self.assertEqual(out["level"], "NONE")
		self.assertEqual(out["repo_count"], 0)

	def test_content_hashes_are_identical(self):
		h = self.fn("_content_hash")
		self.assertEqual(h("torvalds", "C", "EXPERT", 8, 999), SV._content_hash("torvalds", "C", "EXPERT", 8, 999))

	def test_validation_is_identical(self):
		up = self.fn("_username_problem")
		sp = self.fn("_skill_problem")
		for value in ("torvalds", "", "-x", "a" * 40, "a/b", None, 5):
			self.assertEqual(bool(up(value)), bool(SV._username_problem(value)), repr(value))
			self.assertEqual(bool(sp(value)), bool(SV._skill_problem(value)), repr(value))

	# ── a full lifecycle driven through the artifact ────────────────────

	def test_full_lifecycle_through_the_artifact(self):
		_STRUCT_HINTS[("SkillVerify", "verifications")] = getattr(self.mod, self.name("Verification"))
		reset_world()
		as_sender(OWNER, 0)
		c = self.mod.SkillVerify(0)

		# resolve
		as_sender(ALICE, 0)
		queue_ok("torvalds_C")
		out = jload(c.verify_skill("torvalds", "C"))
		self.assertTrue(out["ok"])
		self.assertEqual(out["level"], "EXPERT")
		self.assertEqual(out["status"], "RESOLVED")

		# the gate
		self.assertTrue(c.is_verified("torvalds", "C", "PROFICIENT"))
		self.assertFalse(c.is_verified("torvalds", "C", "GURU"))

		# refund on reject, from the mangled bytes
		as_sender(BOB, 7)
		before = len(TRANSFERS)
		refused = jload(c.verify_skill("", "C"))
		self.assertFalse(refused["ok"])
		self.assertEqual(TRANSFERS[before:], [(str(BOB), 7)])

		# pending -> stalled
		clock_at(400)
		as_sender(BOB, 0)
		queue_raw(403, RATE_LIMIT_BODY)
		pend = jload(c.verify_skill("gvanrossum", "Python"))
		self.assertEqual(pend["status"], "PENDING")
		clock_at(4000)
		self.assertTrue(jload(c.settle_stalled(pend["verification_id"]))["ok"])
		self.assertEqual(jload(c.get_verification(pend["verification_id"]))["status"], "STALLED")

		# terminal records stay frozen
		frozen = jload(c.get_verification(1))
		self.assertFalse(jload(c.resolve_pending(1))["ok"])
		self.assertEqual(jload(c.get_verification(1))["level"], frozen["level"])

	def test_consumer_lifecycle_through_the_artifact(self):
		_STRUCT_HINTS[("SkillVerify", "verifications")] = getattr(self.mod, self.name("Verification"))
		_STRUCT_HINTS[("SkillConsumer", "bounties")] = getattr(self.cmod, self.cmap.get("Bounty", "Bounty"))
		reset_world()
		as_sender(OWNER, 0)
		oracle = self.mod.SkillVerify(0)
		as_sender(ALICE, 0)
		queue_ok("gvanrossum_Python")
		oracle.verify_skill("gvanrossum", "Python")

		as_sender(OWNER, 0)
		consumer = self.cmod.SkillConsumer(str(_Addr("0x" + "e" * 40)))
		ORACLE["impl"] = oracle

		as_sender(BOB, GEN)
		self.assertTrue(jload(consumer.post_bounty("Port it", "Python", "PROFICIENT"))["ok"])
		as_sender(CAROL, 0)
		before = len(TRANSFERS)
		claim = jload(consumer.claim_bounty(1, "gvanrossum"))
		self.assertTrue(claim["ok"])
		self.assertEqual(TRANSFERS[before:], [(str(CAROL), GEN)])

		# and the exploding-oracle guard survives the mangle
		as_sender(BOB, GEN)
		consumer.post_bounty("Another", "Python", "PROFICIENT")
		ORACLE["raise_on"] = "get_latest"
		as_sender(CAROL, 0)
		before = len(TRANSFERS)
		out = jload(consumer.claim_bounty(2, "gvanrossum"))
		self.assertFalse(out["ok"])
		self.assertEqual(TRANSFERS[before:], [])
		ORACLE["raise_on"] = None

	def test_static_scans_pass_on_the_artifact_too(self):
		tree = ast.parse(ARTIFACT.read_text(encoding="utf8"))
		ctree = ast.parse(CONSUMER_ARTIFACT.read_text(encoding="utf8"))
		self.assertEqual(_nondet_closures_referencing_self(tree), [])
		for t, label in ((tree, "oracle"), (ctree, "consumer")):
			cls = [n for n in t.body if isinstance(n, ast.ClassDef)]
			for c in cls:
				for fn in _methods(c):
					self.assertEqual(_raises_after_write(fn), [], label + "." + fn.name)


if __name__ == "__main__":
	unittest.main(verbosity=1)
