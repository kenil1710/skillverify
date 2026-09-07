# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
from dataclasses import dataclass
import json

# SkillVerify - a developer skill verification oracle.
#
# Ask it "does GitHub user U actually write language L, and how much", and every
# validator answers independently by querying GitHub's search index. What lands
# on chain is a level - EXPERT, PROFICIENT, BEGINNER or NONE - that a quorum of
# validators computed separately and agreed on, plus the evidence they computed
# it from. Any other contract can then gate on it: see SkillConsumer.py.
#
# Measurements behind every design decision: docs/PROBE.md. Hazards and the
# reasoning that is not recoverable from the code: contracts/NOTES.md.
#
# Nothing may sit between line 1 and the import above - GenVM parses the whole
# contiguous leading `#` block as the runner JSON, and a comment there makes the
# contract undeployable with no error reported but `invalid_contract`.
#
# FIVE RULES GOVERN EVERYTHING BELOW. Each was measured or paid for, not assumed.
#
#   1. A PAYABLE METHOD MAY NEVER RAISE. GenVM rolls back contract STATE on a
#      UserError but does NOT return the value that rode in with the call - it
#      stays in the contract, unaccounted for. verify_skill is payable (the fee
#      is 0 today and owner-settable tomorrow), so every rejection is a
#      SUCCESSFUL transaction that refunds and returns {"ok": false}. See
#      _reject. This is why every argument that can reach a storage write is
#      range-checked first.
#
#   2. THE LEVEL IS THE ONLY COMPARED CONSENSUS AXIS. One string. Six possible
#      values: the four levels plus NO_SUCH_USER and UNAVAILABLE. docs/PROBE.md
#      6 measured that the counts happen to agree too, and the axis still does
#      not include them - a verification that lands UNDETERMINED because one
#      validator's search shard was a second stale is a worse outcome than one
#      whose byte count is a second stale.
#
#   3. GITHUB'S ANSWER IS NEVER TRUSTED ON ITS WORD. `language:` qualifiers it
#      does not recognise are SILENTLY IGNORED and the user's whole repository
#      list comes back 200 (docs/PROBE.md 5). `total_count` therefore certifies
#      anybody as EXPERT in any typo. _score re-checks every returned item
#      against its own `language` field and counts only what matches.
#
#   4. A FULL RATE-LIMIT BUCKET IS NOT AN ANSWER. Every validator egresses from
#      ONE IP into a shared quota (docs/PROBE.md 2). A 403 means "ask again in a
#      minute", and scoring it as NONE would certify a real expert as unskilled.
#      Those verifications are stored PENDING and re-resolved; they are never
#      scored.
#
#   5. A RESOLVED OR STALLED VERIFICATION IS FROZEN FOREVER. No method, owner
#      included, may write to a record in a terminal status. _mutable is the one
#      gate, and test_logic.py parses this file to prove every mutator passes
#      through it.

# ---------------------------------------------------------------- the ladder
LEVEL_EXPERT = "EXPERT"
LEVEL_PROFICIENT = "PROFICIENT"
LEVEL_BEGINNER = "BEGINNER"
LEVEL_NONE = "NONE"

# Ascending. The index IS the rank, so _rank and _levels_at_or_above never
# disagree about the ordering - there is only one ordering in the file.
LEVELS = (LEVEL_NONE, LEVEL_BEGINNER, LEVEL_PROFICIENT, LEVEL_EXPERT)

EXPERT_REPOS = 5
EXPERT_BYTES = 1000
PROFICIENT_REPOS = 3
PROFICIENT_BYTES = 500
BEGINNER_REPOS = 1

# ------------------------------------------------- the consensus axis, in full
# Six values, one string. The two below are NOT levels and are never stored as
# one: NO_SUCH_USER becomes a RESOLVED record at level NONE carrying
# user_found=false, and UNAVAILABLE becomes a PENDING record carrying no level
# at all.
AXIS_NO_SUCH_USER = "NO_SUCH_USER"
AXIS_UNAVAILABLE = "UNAVAILABLE"
AXIS_VALUES = (LEVEL_EXPERT, LEVEL_PROFICIENT, LEVEL_BEGINNER, LEVEL_NONE, AXIS_NO_SUCH_USER, AXIS_UNAVAILABLE)

# ------------------------------------------------------------------- statuses
STATUS_PENDING = "PENDING"
STATUS_RESOLVED = "RESOLVED"
STATUS_STALLED = "STALLED"
TERMINAL_STATUSES = (STATUS_RESOLVED, STATUS_STALLED)

# ------------------------------------------------------------------- limits
MAX_USERNAME = 39          # GitHub's own ceiling
MAX_SKILL = 40             # "Jupyter Notebook" is 16; 40 leaves room and bounds the URL
MAX_TOP_REPOS = 3
MAX_REPO_NAME = 100        # GitHub's own ceiling
SEARCH_PAGE = 100          # one page; the ladder saturates at 5 repos (NOTES.md 4)
MAX_ITEMS_SCANNED = 100

DEFAULT_FEE = 0            # free on testnet; set_fee exists for later
MAX_FEE = 10**18           # 1 GEN - a ceiling the owner cannot price users out past
DEFAULT_COOLDOWN = 300     # seconds between verifications from one wallet
MAX_COOLDOWN = 86400
DEFAULT_RESOLVE_WINDOW = 3600   # a PENDING record may be settled stalled after this
MIN_RESOLVE_WINDOW = 60
MAX_RESOLVE_WINDOW = 30 * 86400
DEFAULT_FRESHNESS = 0      # 0 = a verification never expires
MAX_FRESHNESS = 365 * 86400

MAX_PAGE = 50              # listing views return at most this many rows
MAX_ATTEMPTS = 1000        # bound on the per-record resolve counter

# What `total_bytes` MEANS, carried on every record and returned by get_config.
# It is the summed on-disk size of the matching repositories, not a Linguist
# byte count - the endpoint that produces the latter costs one request per
# repository and docs/PROBE.md 2 measured that budget as unaffordable. Labelling
# it beats overstating it by 4x in silence.
BYTES_BASIS = "github_repo_size_kb"

GITHUB_SEARCH = "https://api.github.com/search/repositories"

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

# Percent-encoding keeps these bytes and encodes everything else. RFC 3986
# unreserved set. `+` and `#` are deliberately NOT here: docs/PROBE.md 4
# measured `language:C++` returning eight repositories every one of which is
# tagged `C`, and `language:C#` returning 164 of them - GitHub reads the `+` as
# a space and the `#` as the start of a fragment, and answers 200 either way.
UNRESERVED = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
HEX = "0123456789ABCDEF"


# ══════════════════════════════════════════════════════════════════════════
# Pure module-level helpers.
#
# Module level, not methods, for a reason that costs a whole debugging session
# to rediscover: a closure passed to gl.vm.run_nondet that references `self`
# PICKLES CONTRACT STORAGE into the nondeterministic block and kills the leader
# at `run_time 0s` with no useful error. Every value a closure needs is copied
# through str()/int() first. It is also what lets test_logic.py exercise this
# entire surface offline in milliseconds.
#
# NONE OF THEM RAISES, FOR ANY INPUT. verify_skill is payable, and a helper that
# raises on a malformed argument is rule 1's fund-loss bug arriving through the
# front door. test_logic.py fuzzes every one of them with None, dicts, bytes and
# 5,000-character strings and asserts no exception escapes.
# ══════════════════════════════════════════════════════════════════════════


def _as_int(value, fallback: int) -> int:
	try:
		if isinstance(value, bool):
			return fallback
		return int(value)
	except Exception:
		return fallback


def _as_text(value) -> str:
	"""Text, with None mapping to "" rather than to "None".

	str(None) is the four-character string "None", and `_normalize_username`
	would lowercase that into the perfectly legal GitHub username `none` - so a
	missing argument would stop being an error and start being a lookup of
	somebody else's account. The same slip in `_score` would make a repository
	GitHub could not classify match the claimed skill "none". Both are silent
	wrong answers rather than failures, which is the worst kind."""
	if value is None:
		return ""
	if isinstance(value, str):
		return value
	try:
		return str(value)
	except Exception:
		return ""


def _clamp(value: int, low: int, high: int) -> int:
	if value < low:
		return low
	if value > high:
		return high
	return value


def _days_from_civil(y: int, m: int, d: int) -> int:
	y -= 1 if m <= 2 else 0
	era = (y if y >= 0 else y - 399) // 400
	yoe = y - era * 400
	doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
	doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
	return era * 146097 + doe - 719468


def _epoch_from_iso(value: str) -> int:
	"""Seconds since the epoch from the block's ISO datetime. Returns 0 rather
	than raising for anything unparseable - the caller treats 0 as "no clock",
	and a raise here would reach a payable path."""
	if not isinstance(value, str) or len(value) < 19:
		return 0
	try:
		year = int(value[0:4])
		month = int(value[5:7])
		day = int(value[8:10])
		hour = int(value[11:13])
		minute = int(value[14:16])
		second = int(value[17:19])
	except Exception:
		return 0
	if month < 1 or month > 12 or day < 1 or day > 31:
		return 0
	if hour > 23 or minute > 59 or second > 60:
		return 0
	return _days_from_civil(year, month, day) * 86400 + hour * 3600 + minute * 60 + second


def _fnv(text: str) -> str:
	"""FNV-1a, written out by hand.

	Python's built-in hash() is SEEDED PER PROCESS, so a leader and its
	validators would compute different digests for identical input and disagree
	for no reason at all. Masked to 64 bits at every step and returned as hex
	TEXT so nothing meets a sized integer mid-computation, where a GenVM
	overflow would kill the transaction."""
	if not isinstance(text, str):
		return ""
	if text == "":
		return ""
	h = 0xCBF29CE484222325
	for byte in text.encode("utf-8"):
		h = ((h ^ byte) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
	return "%016x" % h


def _content_hash(username: str, skill: str, level: str, repo_count: int, total_bytes: int) -> str:
	"""The record's fingerprint, over exactly the five fields the plan names.

	Field-separated with a byte that cannot occur in any of them, so
	("ab", "c") and ("a", "bc") cannot collide - a hash built by concatenation
	is a hash that can be forged by moving a character across a boundary."""
	parts = [
		_normalize_username(username),
		_normalize_skill(skill),
		_as_text(level),
		str(_as_int(repo_count, 0)),
		str(_as_int(total_bytes, 0)),
	]
	return _fnv("\x1f".join(parts))


def _normalize_username(value) -> str:
	"""GitHub usernames are case-insensitive, so `Torvalds` and `torvalds` are
	one identity and must index to one bucket. Lowercased and trimmed."""
	text = _as_text(value).strip()
	return text.lower()[:MAX_USERNAME]


def _normalize_skill(value) -> str:
	"""Lowercased, trimmed, and internal whitespace collapsed to single spaces -
	so "  Jupyter   Notebook " and "jupyter notebook" are one skill and one
	index bucket. The DISPLAY spelling is kept separately on the record."""
	return " ".join(_as_text(value).split()).lower()[:MAX_SKILL]


def _display_skill(value) -> str:
	return " ".join(_as_text(value).split())[:MAX_SKILL]


def _username_problem(value) -> str:
	"""Why this username cannot be used, or "" if it can.

	GitHub's own rules: alphanumerics and single hyphens, no leading or trailing
	hyphen, 1-39 characters. Enforcing them here means a malformed name is
	refused for free instead of spending a validator's scarce search quota to
	be told 422."""
	text = _as_text(value).strip()
	if text == "":
		return "github_username is empty"
	if len(text) > MAX_USERNAME:
		return "github_username exceeds " + str(MAX_USERNAME) + " characters"
	lowered = text.lower()
	for ch in lowered:
		if not (("a" <= ch <= "z") or ("0" <= ch <= "9") or ch == "-"):
			return "github_username may only contain letters, digits and hyphens"
	if lowered.startswith("-") or lowered.endswith("-"):
		return "github_username may not start or end with a hyphen"
	if lowered.find("--") >= 0:
		return "github_username may not contain consecutive hyphens"
	return ""


def _skill_problem(value) -> str:
	"""Why this skill cannot be used, or "" if it can.

	The charset is a whitelist rather than a blacklist because the value is
	interpolated into a URL. `+` and `#` are ALLOWED - C++ and C# are two of the
	most claimed skills there are - and are made safe by _pct rather than by
	being banned. What is banned is anything that could restructure the query
	itself: quotes, ampersands, colons and control characters."""
	text = _as_text(value)
	collapsed = " ".join(text.split())
	if collapsed == "":
		return "skill is empty"
	if len(collapsed) > MAX_SKILL:
		return "skill exceeds " + str(MAX_SKILL) + " characters"
	for ch in collapsed.lower():
		ok = ("a" <= ch <= "z") or ("0" <= ch <= "9") or ch in " +#-._"
		if not ok:
			return "skill may only contain letters, digits, spaces and + # - . _"
	return ""


def _pct(value: str) -> str:
	"""Percent-encode for a URL query VALUE.

	This function is the difference between verifying C++ and verifying C.
	docs/PROBE.md 4: `q=user:nlohmann+language:C++` answers 200 with one
	repository tagged `C`, where the correct answer is eight tagged `C++`. The
	`+` is a space to a query parser and GitHub then reads a truncated
	qualifier - it does not complain, it answers the wrong question. Everything
	outside RFC 3986's unreserved set is encoded, including the space, so no
	byte in a user-supplied skill can be read as query syntax."""
	if not isinstance(value, str):
		return ""
	out = []
	for byte in value.encode("utf-8"):
		ch = chr(byte)
		if ch in UNRESERVED:
			out.append(ch)
		else:
			out.append("%" + HEX[(byte >> 4) & 0xF] + HEX[byte & 0xF])
	return "".join(out)


def _search_url(username: str, skill: str) -> str:
	"""The one request a verification costs.

	  q=user:{U} language:"{L}"   with every byte percent-encoded

	Three measured decisions are frozen into this line:

	  - The language value is ALWAYS QUOTED. A multi-word language must be
	    (`language:"Jupyter Notebook"` finds 31 repositories, unquoted finds 7
	    because the second word becomes a free-text term), and docs/PROBE.md 5
	    measured that quoting a single word changes nothing - `language:"C"` and
	    `language:C` both return the same 8. One code path, no branch to get
	    wrong.

	  - `%20` separates the qualifiers, never `+`. A literal `+` is a space to
	    the parser, which is the same trap by another route.

	  - `fork:true` is NOT passed, so GitHub's default applies and FORKS ARE
	    EXCLUDED. That closes a hole rather than opening one: forking forty C
	    repositories would otherwise score EXPERT in C without a line written.
	    torvalds is 8 repositories without it and 10 with."""
	user = _pct(_normalize_username(username))
	lang = _pct(_normalize_skill(skill))
	q = "user:" + user + "%20language:%22" + lang + "%22"
	return GITHUB_SEARCH + "?per_page=" + str(SEARCH_PAGE) + "&sort=updated&q=" + q


def _rank(level) -> int:
	"""Position on the ladder, -1 for anything that is not a level. Callers
	branch on the -1 rather than being handed a plausible 0, because NONE is a
	real level and "not a level at all" must not silently mean NONE."""
	text = _as_text(level)
	for i in range(len(LEVELS)):
		if LEVELS[i] == text:
			return i
	return -1


def _level_for(repo_count: int, total_bytes: int) -> str:
	"""The ladder, exactly as specified. Falls THROUGH rather than branching:
	five repositories that are all empty fail the EXPERT byte floor, then fail
	the PROFICIENT byte floor, and land at BEGINNER - which is the right answer
	and is not what a chain of elifs on repo count alone would give."""
	repos = _as_int(repo_count, 0)
	size = _as_int(total_bytes, 0)
	if repos >= EXPERT_REPOS and size >= EXPERT_BYTES:
		return LEVEL_EXPERT
	if repos >= PROFICIENT_REPOS and size >= PROFICIENT_BYTES:
		return LEVEL_PROFICIENT
	if repos >= BEGINNER_REPOS:
		return LEVEL_BEGINNER
	return LEVEL_NONE


def _score(document, skill: str) -> dict:
	"""Turn a GitHub search response into a level. THE LOAD-BEARING FUNCTION.

	Rule 3 lives here. `total_count` is read and reported but NEVER scored,
	because GitHub silently ignores a `language:` qualifier it does not
	recognise and returns the user's entire repository list with a 200
	(docs/PROBE.md 5). Scoring that number makes `verify_skill("torvalds",
	"Blockchain")` return EXPERT, and nothing about the transaction looks wrong.

	So every returned item is re-checked against ITS OWN `language` field and
	only exact (case-insensitive) matches are counted. An unrecognised qualifier
	yields zero matches and NONE, which is the correct answer. The discrepancy
	stays visible: the record stores GitHub's `total_count` as `index_count`
	beside the count that was actually earned.

	Ordering is total and deterministic - bytes descending, then name
	ascending - because two validators sorting a tie differently would produce
	different top_repos, and the content hash covers the level rather than the
	list precisely so that a tie cannot cost a round."""
	lang = _normalize_skill(skill)
	if not isinstance(document, dict):
		return {"ok": False, "repo_count": 0, "total_bytes": 0, "index_count": 0, "top_repos": [], "level": LEVEL_NONE}
	items = document.get("items")
	if not isinstance(items, list):
		items = []
	matched = []
	total = 0
	for entry in items[:MAX_ITEMS_SCANNED]:
		if not isinstance(entry, dict):
			continue
		# The re-check. `language` is null for a repository GitHub could not
		# classify; str(None) is "none", which matches no real language.
		if _normalize_skill(entry.get("language")) != lang:
			continue
		size_kb = entry.get("size", 0)
		if isinstance(size_kb, bool) or not isinstance(size_kb, int):
			size_kb = 0
		size_kb = _clamp(int(size_kb), 0, 1 << 40)
		name = _as_text(entry.get("name"))[:MAX_REPO_NAME]
		matched.append({"name": name, "bytes": size_kb * 1024})
		total += size_kb * 1024
	matched.sort(key=lambda row: (-row["bytes"], row["name"]))
	return {
		"ok": True,
		"repo_count": len(matched),
		"total_bytes": total,
		"index_count": _clamp(_as_int(document.get("total_count", 0), 0), 0, 1 << 40),
		"incomplete": bool(document.get("incomplete_results", False)),
		"top_repos": [row["name"] for row in matched[:MAX_TOP_REPOS]],
		"level": _level_for(len(matched), total),
	}


def _count_of(bucket) -> int:
	"""len() of a storage bucket that may be absent. On chain an unwritten
	DynArray-valued TreeMap key answers an EMPTY ARRAY; a stub answers None.
	Both mean zero, and `is None` is wrong for the first of them."""
	if bucket is None:
		return 0
	try:
		return len(bucket)
	except Exception:
		return 0


def _top_list(raw) -> list:
	"""The stored top_repos JSON, back as a list. Defensive both ways: a record
	written before the field existed reads as "", and a record that somehow
	holds a non-array reads as empty rather than propagating a type error into
	every view that touches it."""
	text = _as_text(raw)
	if text == "":
		return []
	try:
		parsed = json.loads(text)
	except Exception:
		return []
	if not isinstance(parsed, list):
		return []
	return [_as_text(name)[:MAX_REPO_NAME] for name in parsed[:MAX_TOP_REPOS]]


def _status_of(res) -> int:
	s = getattr(res, "status_code", None)
	if s is None:
		s = getattr(res, "status", None)
	if s is None:
		return 0
	return _as_int(s, 0)


def _body_of(res) -> str:
	b = getattr(res, "body", None)
	if b is None:
		b = getattr(res, "text", None)
	if b is None:
		return ""
	if isinstance(b, bytes):
		return b.decode("utf-8", errors="ignore")
	return _as_text(b)


def _evaluate(username: str, skill: str) -> dict:
	"""ONE HTTP REQUEST, and the whole verification derived from it.

	Runs on the leader and, unchanged, on every validator. Returns a dict whose
	`axis` field is the ONLY thing consensus compares.

	The status classification is the part that matters, and it is rule 4:

	  200        the index answered            -> a level
	  422        no such user, or unsearchable -> NO_SUCH_USER (permanent)
	  403 / 429  the shared bucket is full     -> UNAVAILABLE (ask again)
	  5xx / 0    GitHub is having a moment     -> UNAVAILABLE
	  other 4xx  something we sent was wrong   -> UNAVAILABLE, never a score

	403 is the one that would do real damage if it were mistaken for an answer.
	Every validator egresses from a single IP (44.198.152.104) into one 60/hour
	bucket, so a full bucket is an ordinary Tuesday, and scoring it NONE would
	certify a working developer as having no skill - permanently, on chain.

	NEVER RAISES. A raise inside a nondet block reaches verify_skill, which is
	payable. Even the JSON parse is guarded."""
	url = _search_url(username, skill)
	try:
		try:
			res = gl.nondet.web.request(url, method="GET")
		except AttributeError:
			res = gl.nondet.web.get(url)
		status = _status_of(res)
		body = _body_of(res)
	except Exception as exc:
		return {"axis": AXIS_UNAVAILABLE, "status": 0, "reason": "fetch failed: " + _as_text(exc)[:160]}

	if status == 422:
		return {"axis": AXIS_NO_SUCH_USER, "status": status, "reason": "GitHub cannot search this user"}
	if status != 200:
		return {"axis": AXIS_UNAVAILABLE, "status": status, "reason": "GitHub answered " + str(status)}

	try:
		document = json.loads(body)
	except Exception:
		# A 200 that is not JSON is an interstitial or a truncated body, not an
		# answer. Treated as transient so it is retried rather than scored.
		return {"axis": AXIS_UNAVAILABLE, "status": status, "reason": "response was not JSON"}

	scored = _score(document, skill)
	if not scored["ok"]:
		return {"axis": AXIS_UNAVAILABLE, "status": status, "reason": "response had no items array"}
	return {
		"axis": scored["level"],
		"status": status,
		"repo_count": scored["repo_count"],
		"total_bytes": scored["total_bytes"],
		"index_count": scored["index_count"],
		"incomplete": scored["incomplete"],
		"top_repos": scored["top_repos"],
		"reason": "",
	}


def _axis_of(result) -> str:
	"""The compared value, pulled out defensively. Anything that is not one of
	the six known axis values reads as UNAVAILABLE, so a malformed payload can
	never be mistaken for a level."""
	if not isinstance(result, dict):
		return AXIS_UNAVAILABLE
	axis = _as_text(result.get("axis"))
	if axis in AXIS_VALUES:
		return axis
	return AXIS_UNAVAILABLE


def _run_evaluation(username: str, skill: str) -> dict:
	"""The nondeterministic block, with its equivalence principle.

	Copies both arguments through str() BEFORE the closures are built, so
	neither closure captures `self` or any storage handle - that pickles
	contract storage into the nondet block and kills the leader at
	`run_time 0s` with no error worth reading.

	The validator RE-RUNS the whole evaluation - its own HTTP request, its own
	parse, its own scoring - and compares one string. It never inspects the
	leader's payload for well-formedness and calls that agreement; a validator
	that only checks the leader's JSON shape has verified nothing.

	A LEADER ERROR IS RE-RUN, NEVER VOTED False. Answering False on a leader
	exception turns one node's transient failure into a genuine disagreement
	and burns a consensus round for a question both nodes could have answered."""
	user = str(username)
	lang = str(skill)

	def leader_fn() -> dict:
		return _evaluate(user, lang)

	def validator_fn(leader_result: gl.vm.Result) -> bool:
		if not isinstance(leader_result, gl.vm.Return):
			leader_fn()
			return False
		mine = _axis_of(leader_fn())
		theirs = _axis_of(leader_result.calldata)
		return mine == theirs

	outcome = gl.vm.run_nondet(leader_fn, validator_fn)
	if not isinstance(outcome, dict):
		return {"axis": AXIS_UNAVAILABLE, "status": 0, "reason": "nondet returned no document"}
	return outcome


# ══════════════════════════════════════════════════════════════════════════
# Storage
# ══════════════════════════════════════════════════════════════════════════


@allow_storage
@dataclass
class Verification:
	verification_id: u32
	github_username: str      # normalized: lowercase, trimmed
	username_display: str     # as the requester spelled it
	skill: str                # normalized: lowercase, whitespace-collapsed
	skill_display: str        # as the requester spelled it
	status: str               # PENDING | RESOLVED | STALLED
	level: str                # "" until RESOLVED
	repo_count: u32
	total_bytes: u128
	index_count: u32          # GitHub's total_count - see _score
	# A JSON array of names, NOT a DynArray[str]. Storing three short strings
	# does not justify a storage collection whose element-removal API this
	# project has never exercised on chain, and the JSON round-trip is exact.
	top_repos: str
	content_hash: str
	verified_at: u64          # 0 until RESOLVED
	verified_by: Address      # who requested it
	requested_at: u64
	# Frozen at request time. The owner's setters move the DEFAULTS for later
	# verifications and can never reach a record that already exists.
	resolve_window: u64
	fee_paid: u128
	fee_snapshot: u128
	bytes_basis: str
	# Advisory, and never load-bearing.
	attempts: u32
	user_found: bool
	incomplete_index: bool
	last_reason: str
	http_status: u32


@gl.evm.contract_interface
class _Payee:
	"""An EOA payout handle. An external value transfer needs an EVM contract
	interface even when there is no contract at the address. Transfers apply on
	FINALIZATION, not on acceptance."""

	class View:
		pass

	class Write:
		pass


class SkillVerify(gl.Contract):
	owner: Address
	paused: bool

	verifications: TreeMap[u32, Verification]
	verification_ids: DynArray[u32]
	next_id: u32

	# "user\x1fskill" -> ids, newest last. \x1f cannot occur in either half
	# (both are whitelist-validated), so two different pairs cannot collide on
	# one key by moving a character across the boundary.
	by_pair: TreeMap[str, DynArray[u32]]
	by_user: TreeMap[str, DynArray[u32]]
	by_skill: TreeMap[str, DynArray[u32]]
	# The newest RESOLVED id for a pair. is_verified reads this and never walks.
	latest_resolved: TreeMap[str, u32]
	# The in-flight PENDING id for a pair, +1 so that 0 means "none" and
	# verification 0 is still expressible.
	inflight: TreeMap[str, u32]

	last_request_at: TreeMap[Address, u64]

	fee: u128
	cooldown: u64
	resolve_window: u64
	freshness_window: u64

	total_verifications: u32
	# Maintained as verifications land rather than counted on read. len() over
	# a TreeMap is not an API this project has exercised on chain, and a view
	# that walks every bucket is one that works until it does not.
	distinct_users: u32
	distinct_skills: u32
	distinct_pairs: u32
	total_resolved: u32
	total_stalled: u32
	total_pending: u32
	fees_collected: u128
	fees_withdrawn: u128
	total_refunded: u128

	def __init__(self, fee: int = DEFAULT_FEE):
		self.owner = gl.message.sender_address
		self.paused = False
		self.next_id = u32(1)
		# Clamped, not validated-and-raised: a constructor that reverts on a
		# fat-fingered argument costs a deploy, and there is no caller to read
		# a rejection message.
		self.fee = u128(_clamp(_as_int(fee, DEFAULT_FEE), 0, MAX_FEE))
		self.cooldown = u64(DEFAULT_COOLDOWN)
		self.resolve_window = u64(DEFAULT_RESOLVE_WINDOW)
		self.freshness_window = u64(DEFAULT_FRESHNESS)
		self.total_verifications = u32(0)
		self.distinct_users = u32(0)
		self.distinct_skills = u32(0)
		self.distinct_pairs = u32(0)
		self.total_resolved = u32(0)
		self.total_stalled = u32(0)
		self.total_pending = u32(0)
		self.fees_collected = u128(0)
		self.fees_withdrawn = u128(0)
		self.total_refunded = u128(0)

	# ─────────────────────────────────────────────────────────── internals

	def _now(self) -> int:
		return _epoch_from_iso(gl.message_raw.get("datetime", ""))

	def _pay(self, to: Address, amount: int) -> None:
		if amount <= 0:
			return
		_Payee(Address(str(to))).emit_transfer(value=u256(int(amount)))

	def _reject(self, sender: Address, value: int, reason: str) -> str:
		"""Refund a payable call and RETURN. Rule 1, and the single most
		important method in this file.

		GenVM rolls back contract STATE on a UserError but does NOT return the
		value that rode in with the call: it stays in the contract, unaccounted
		for and unreachable. So a rejection must be a SUCCESSFUL transaction
		that happens to refund. Raising here - even AFTER the transfer below -
		would roll the refund back along with everything else and recreate
		exactly the bug this method exists to prevent.

		Every caller must read the returned JSON. `ok: false` is a rejection,
		not a failure to submit: the transaction succeeded.

		The counter is CLAMPED rather than added blindly, because a u128 write
		that overflows RAISES rather than truncating - and a raise on this line
		would roll back the refund. The statistic is expendable; the money is
		not."""
		if value > 0:
			self._pay(sender, value)
			self.total_refunded = u128(_clamp(int(self.total_refunded) + value, 0, (1 << 128) - 1))
		return json.dumps({"ok": False, "reason": reason, "refunded": str(value)})

	def _pair_key(self, username: str, skill: str) -> str:
		return _normalize_username(username) + "\x1f" + _normalize_skill(skill)

	def _find(self, verification_id: int):
		"""The record, or None. DOES NOT RAISE.

		PredictStake shipped the raising version of this and its consumer's
		payable method confiscated a premium the first time somebody asked
		about a market that did not exist: the raise crossed the contract
		boundary and reverted the caller, keeping the value. A view that raises
		is a liability to every contract that composes with it, so an unknown id
		is an absence here and a `found: false` document at the surface."""
		return self.verifications.get(u32(_clamp(_as_int(verification_id, -1), 0, (1 << 32) - 1)))

	def _mutable(self, record) -> bool:
		"""Rule 5, the ONE gate. A RESOLVED or STALLED verification is frozen
		forever - no method, owner included, may write to it.

		test_logic.py parses this file and asserts that every method which
		writes to a Verification field passes through this call first. That test
		is the reason the gate is a named method rather than an inline
		comparison repeated in three places: an inline check can be forgotten in
		the fourth."""
		if record is None:
			return False
		return str(record.status) not in TERMINAL_STATUSES

	def _index(self, key: str, table, verification_id: int) -> bool:
		"""Append an id to a bucket. Returns True if the bucket was EMPTY, which
		is what the distinct_* counters are incremented on.

		Emptiness is measured with len(), not with `is None`. A TreeMap whose
		value type is a DynArray answers a missing key with an EMPTY ARRAY on
		chain, so `is None` would report every first-ever bucket as
		pre-existing and every distinct counter would stay at zero forever."""
		bucket = table.get_or_insert_default(key)
		first = len(bucket) == 0
		bucket.append(u32(verification_id))
		return first

	def _bump(self, field_value: int) -> int:
		return _clamp(field_value + 1, 0, (1 << 32) - 1)

	def _summary(self, record) -> dict:
		"""One shape for every view that returns a verification, so a field
		added here appears everywhere at once and cannot go missing from the
		listing that a consumer happens to read."""
		now = self._now()
		verified_at = int(record.verified_at)
		age = (now - verified_at) if (verified_at > 0 and now > verified_at) else 0
		return {
			"verification_id": int(record.verification_id),
			"github_username": str(record.github_username),
			"username_display": str(record.username_display),
			"skill": str(record.skill),
			"skill_display": str(record.skill_display),
			"status": str(record.status),
			"level": str(record.level),
			"level_rank": _rank(str(record.level)),
			"repo_count": int(record.repo_count),
			"total_bytes": str(int(record.total_bytes)),
			"bytes_basis": str(record.bytes_basis),
			"index_count": int(record.index_count),
			"top_repos": _top_list(str(record.top_repos)),
			"content_hash": str(record.content_hash),
			"verified_at": verified_at,
			"verified_by": str(record.verified_by),
			"requested_at": int(record.requested_at),
			"age_seconds": age,
			"stale": bool(int(self.freshness_window) > 0 and verified_at > 0 and age > int(self.freshness_window)),
			"resolve_window": int(record.resolve_window),
			"settle_stalled_at": int(record.requested_at) + int(record.resolve_window),
			"fee_paid": str(int(record.fee_paid)),
			"fee_snapshot": str(int(record.fee_snapshot)),
			"attempts": int(record.attempts),
			"user_found": bool(record.user_found),
			"incomplete_index": bool(record.incomplete_index),
			"last_reason": str(record.last_reason),
			"http_status": int(record.http_status),
		}

	def _apply(self, record, outcome: dict) -> dict:
		"""Write an evaluation onto a record. THE ONLY PLACE A LEVEL IS STORED.

		Called from verify_skill and from resolve_pending so the two can never
		drift apart, and structured so that everything which could refuse
		happens BEFORE the first field is written:

		  - the caller has already checked _mutable;
		  - nothing below can raise, so no field is written and then rolled back
		    while a counter somewhere else keeps the increment.

		Every stored field is RECOMPUTED from the agreed evidence rather than
		copied from wherever it was convenient. content_hash in particular is
		derived from the values as stored, so a record whose hash does not match
		its own fields is impossible to produce - which is what makes the hash
		worth checking."""
		axis = _axis_of(outcome)
		status_code = _clamp(_as_int(outcome.get("status"), 0), 0, (1 << 32) - 1)
		reason = _as_text(outcome.get("reason"))[:200]

		if axis == AXIS_UNAVAILABLE:
			# NOT an answer. The record stays PENDING and keeps its level empty.
			record.attempts = u32(_clamp(int(record.attempts) + 1, 0, MAX_ATTEMPTS))
			record.last_reason = reason if reason else "source unavailable"
			record.http_status = u32(status_code)
			return {"resolved": False, "axis": axis, "reason": record.last_reason}

		if axis == AXIS_NO_SUCH_USER:
			level = LEVEL_NONE
			repo_count = 0
			total_bytes = 0
			index_count = 0
			top = []
			found = False
			incomplete = False
		else:
			level = axis
			repo_count = _clamp(_as_int(outcome.get("repo_count"), 0), 0, (1 << 32) - 1)
			total_bytes = _clamp(_as_int(outcome.get("total_bytes"), 0), 0, (1 << 128) - 1)
			index_count = _clamp(_as_int(outcome.get("index_count"), 0), 0, (1 << 32) - 1)
			raw_top = outcome.get("top_repos")
			top = []
			if isinstance(raw_top, list):
				for name in raw_top[:MAX_TOP_REPOS]:
					top.append(_as_text(name)[:MAX_REPO_NAME])
			found = True
			incomplete = bool(outcome.get("incomplete", False))
			# The level is RECOMPUTED from the counts rather than trusted. The
			# leader agreed with its validators on a level and separately
			# reported counts; if those two disagree the counts are the evidence
			# and the level must follow them, or the record would carry a
			# verdict its own evidence does not support.
			level = _level_for(repo_count, total_bytes)

		record.level = level
		record.repo_count = u32(repo_count)
		record.total_bytes = u128(total_bytes)
		record.index_count = u32(index_count)
		record.top_repos = json.dumps(top)
		record.user_found = found
		record.incomplete_index = incomplete
		record.http_status = u32(status_code)
		record.last_reason = reason
		record.attempts = u32(_clamp(int(record.attempts) + 1, 0, MAX_ATTEMPTS))
		record.verified_at = u64(_clamp(self._now(), 0, (1 << 64) - 1))
		record.content_hash = _content_hash(
			str(record.github_username), str(record.skill), level, repo_count, total_bytes,
		)
		record.status = STATUS_RESOLVED
		return {"resolved": True, "axis": axis, "level": level}

	def _release(self, key: str) -> None:
		"""Free the in-flight slot for a pair.

		Writes the 0 sentinel rather than deleting the key. Two reasons, and the
		second is the load-bearing one:

		  - A TreeMap slot holds `id + 1`, so 0 is already the encoding for "no
		    verification in flight" and needs no separate absence signal.
		  - ON CHAIN A TreeMap WITH A SCALAR VALUE TYPE ANSWERS A MISSING KEY WITH
		    THAT TYPE'S ZERO, NOT WITH None. So `if m.get(k) is not None` is TRUE
		    for every key that was never written, and the obvious guarded delete
		    would have called `del` on keys that are not there. The +1 offset makes
		    the absent case and the released case literally the same value, so
		    there is nothing left for the two semantics to disagree about."""
		self.inflight[key] = u32(0)

	def _pending_id(self, key: str) -> int:
		# _as_int(None, 0) and int(0) both give 0, so this reads correctly under
		# BOTH the on-chain semantics (missing key -> u32 zero) and a stub that
		# answers None. -1 means "nothing in flight".
		return _as_int(self.inflight.get(key), 0) - 1

	def _page(self, ids, offset: int, limit: int) -> list:
		"""One bounded walk shared by all three listing views. Newest first.

		Bounded because an unbounded loop over a growing DynArray is a view that
		works for six months and then exceeds the compute limit - at which point
		every consumer reading it starts reverting, including payable ones."""
		start = _clamp(_as_int(offset, 0), 0, 1 << 30)
		count = _as_int(limit, MAX_PAGE)
		if count <= 0 or count > MAX_PAGE:
			count = MAX_PAGE
		if ids is None:
			return []
		rows = []
		total = len(ids)
		i = total - 1 - start
		while i >= 0 and len(rows) < count:
			record = self.verifications.get(u32(int(ids[i])))
			if record is not None:
				rows.append(self._summary(record))
			i -= 1
		return rows

	# ─────────────────────────────────────────────────────────────── writes

	@gl.public.write.payable
	def verify_skill(self, github_username: str, skill: str) -> str:
		"""Verify that a GitHub user writes a language. THE MAIN ENTRY POINT.

		PAYABLE, AND IT NEVER RAISES. The fee is 0 today and owner-settable
		tomorrow, so this method is payable now rather than becoming payable
		later - and rule 1 applies from the first line. Every refusal below
		refunds whatever came in and returns {"ok": false, "reason": ...}. A
		caller that only checks whether the transaction succeeded will read a
		refunded rejection as an acceptance; check the return value.

		Two outcomes are possible on the happy path, and both are successes:

		  RESOLVED - GitHub's search index answered and the validators agreed on
		             a level. The record is final and frozen.
		  PENDING  - the shared rate-limit bucket was full, or GitHub was
		             briefly unreachable. The request is DURABLY RECORDED and
		             costs nothing to retry with resolve_pending. It is not
		             scored, because scoring an empty bucket as NONE would
		             certify a real developer as unskilled (rule 4).

		A transaction that lands UNDETERMINED applies nothing at all - not the
		record, not the counters, not the rate-limit stamp - so a caller is
		never charged a cooldown for a round the validators could not settle."""
		sender = gl.message.sender_address
		value = _as_int(gl.message.value, 0)

		# ── Everything that can refuse happens first, and refuses by
		# ── refunding. No storage is written above this line.
		if self.paused:
			return self._reject(sender, value, "contract is paused")

		problem = _username_problem(github_username)
		if problem:
			return self._reject(sender, value, problem)
		problem = _skill_problem(skill)
		if problem:
			return self._reject(sender, value, problem)

		fee = int(self.fee)
		if value < fee:
			return self._reject(sender, value, "fee is " + str(fee) + " and " + str(value) + " was sent")

		now = self._now()
		cooldown = int(self.cooldown)
		# 0 means "never seen this wallet", which is what an unwritten scalar
		# TreeMap key answers on chain. `is not None` would match every wallet.
		last = _as_int(self.last_request_at.get(sender), 0)
		if cooldown > 0 and last > 0 and now > 0:
			elapsed = now - last
			if 0 <= elapsed < cooldown:
				return self._reject(sender, value, "rate limited, " + str(cooldown - elapsed) + "s remaining")

		key = self._pair_key(github_username, skill)
		pending = self._pending_id(key)
		if pending >= 0:
			return self._reject(
				sender, value,
				"verification " + str(pending) + " for this username and skill is already in flight",
			)

		if int(self.next_id) >= (1 << 32) - 1:
			return self._reject(sender, value, "verification id space is exhausted")

		# ── The nondeterministic block. It cannot raise (see _evaluate) and
		# ── nothing has been written yet, so an UNDETERMINED round leaves no
		# ── trace whatsoever.
		outcome = _run_evaluation(_normalize_username(github_username), _normalize_skill(skill))

		# ── COMMIT. From here to the return there is no raise, no rejection and
		# ── no early exit, which is what makes the counters below honest: they
		# ── count things that happened.
		verification_id = int(self.next_id)
		self.next_id = u32(verification_id + 1)

		record = self.verifications.get_or_insert_default(u32(verification_id))
		record.verification_id = u32(verification_id)
		record.github_username = _normalize_username(github_username)
		record.username_display = _as_text(github_username).strip()[:MAX_USERNAME]
		record.skill = _normalize_skill(skill)
		record.skill_display = _display_skill(skill)
		record.status = STATUS_PENDING
		record.level = ""
		record.repo_count = u32(0)
		record.total_bytes = u128(0)
		record.index_count = u32(0)
		record.content_hash = ""
		record.top_repos = "[]"
		record.verified_at = u64(0)
		record.verified_by = sender
		record.requested_at = u64(_clamp(now, 0, (1 << 64) - 1))
		record.resolve_window = u64(int(self.resolve_window))
		record.fee_paid = u128(_clamp(fee, 0, (1 << 128) - 1))
		record.fee_snapshot = u128(_clamp(fee, 0, (1 << 128) - 1))
		record.bytes_basis = BYTES_BASIS
		record.attempts = u32(0)
		record.user_found = False
		record.incomplete_index = False
		record.last_reason = ""
		record.http_status = u32(0)

		self.verification_ids.append(u32(verification_id))
		if self._index(record.github_username, self.by_user, verification_id):
			self.distinct_users = u32(self._bump(int(self.distinct_users)))
		if self._index(record.skill, self.by_skill, verification_id):
			self.distinct_skills = u32(self._bump(int(self.distinct_skills)))
		if self._index(key, self.by_pair, verification_id):
			self.distinct_pairs = u32(self._bump(int(self.distinct_pairs)))
		self.total_verifications = u32(self._bump(int(self.total_verifications)))
		self.last_request_at[sender] = u64(_clamp(now, 0, (1 << 64) - 1))
		self.fees_collected = u128(_clamp(int(self.fees_collected) + fee, 0, (1 << 128) - 1))

		applied = self._apply(record, outcome)
		if applied["resolved"]:
			self.latest_resolved[key] = u32(verification_id)
			self.total_resolved = u32(self._bump(int(self.total_resolved)))
			self._release(key)
		else:
			self.inflight[key] = u32(verification_id + 1)
			self.total_pending = u32(self._bump(int(self.total_pending)))

		# Overpayment is returned. The fee is what the fee is; a caller who
		# sends more is not donating.
		change = value - fee
		if change > 0:
			self._pay(sender, change)

		return json.dumps({
			"ok": True,
			"verification_id": verification_id,
			"status": str(record.status),
			"level": str(record.level),
			"repo_count": int(record.repo_count),
			"total_bytes": str(int(record.total_bytes)),
			"top_repos": _top_list(str(record.top_repos)),
			"content_hash": str(record.content_hash),
			"user_found": bool(record.user_found),
			"reason": str(record.last_reason),
			"change_returned": str(change if change > 0 else 0),
		})

	@gl.public.write
	def resolve_pending(self, verification_id: int) -> str:
		"""Re-run the evaluation for a PENDING verification.

		Permissionless on purpose. A verification that met a full rate-limit
		bucket belongs to whoever needs it resolved, not to whoever happened to
		submit it - making this owner-only or requester-only would leave a
		record stuck because one address went away.

		NOT payable and it takes no value, so a revert here costs the caller
		gas and nothing else. It deliberately still does not revert on the
		ordinary refusals: a caller reading `ok: false` learns why, where a bare
		revert would only say that something went wrong.

		Runs during a pause. Pause stops new risk arriving; it must never trap a
		record that already exists in a state it cannot leave."""
		record = self._find(verification_id)
		if record is None:
			return json.dumps({"ok": False, "reason": "unknown verification_id"})
		if not self._mutable(record):
			return json.dumps({
				"ok": False,
				"reason": "verification is " + str(record.status) + " and can never change",
				"status": str(record.status),
				"level": str(record.level),
			})
		if int(record.attempts) >= MAX_ATTEMPTS:
			return json.dumps({"ok": False, "reason": "attempt ceiling reached, settle it stalled"})

		key = self._pair_key(str(record.github_username), str(record.skill))
		outcome = _run_evaluation(str(record.github_username), str(record.skill))

		# ── COMMIT. No raise and no early return below this line.
		applied = self._apply(record, outcome)
		if applied["resolved"]:
			self.latest_resolved[key] = u32(int(record.verification_id))
			self.total_resolved = u32(self._bump(int(self.total_resolved)))
			self.total_pending = u32(_clamp(int(self.total_pending) - 1, 0, (1 << 32) - 1))
			self._release(key)
		return json.dumps({
			"ok": True,
			"verification_id": int(record.verification_id),
			"status": str(record.status),
			"level": str(record.level),
			"repo_count": int(record.repo_count),
			"total_bytes": str(int(record.total_bytes)),
			"content_hash": str(record.content_hash),
			"attempts": int(record.attempts),
			"reason": str(record.last_reason),
		})

	@gl.public.write
	def settle_stalled(self, verification_id: int) -> str:
		"""Close a PENDING verification that has outlived its resolution window.

		The backstop for a source that never comes back. Without it a pair whose
		verification met a permanently-broken GitHub would hold its in-flight
		slot forever and NOBODY could ever verify that username and skill again
		- the anti-duplicate guard would have become a denial of service.

		Permissionless, and it RUNS DURING A PAUSE for the same reason
		resolve_pending does. An owner who could pause and thereby prevent
		stalled records from being cleared would hold exactly the power the
		pause is meant not to include.

		The window is the one FROZEN ON THE RECORD at request time, not the
		current default: an owner who lengthened the window afterwards cannot
		reach backwards and keep an old record in flight."""
		record = self._find(verification_id)
		if record is None:
			return json.dumps({"ok": False, "reason": "unknown verification_id"})
		if not self._mutable(record):
			return json.dumps({
				"ok": False,
				"reason": "verification is already " + str(record.status),
				"status": str(record.status),
			})
		now = self._now()
		due = int(record.requested_at) + int(record.resolve_window)
		if now < due:
			return json.dumps({
				"ok": False,
				"reason": "resolution window has " + str(due - now) + "s left",
				"settle_stalled_at": due,
			})

		# ── COMMIT.
		key = self._pair_key(str(record.github_username), str(record.skill))
		record.status = STATUS_STALLED
		record.level = ""
		record.last_reason = "unresolved after " + str(int(record.resolve_window)) + "s"
		# A stalled record carries NO content hash. The hash certifies a
		# measured result and there was never a measurement; emitting one over
		# an empty level would give an unverified record a verified record's
		# shape.
		record.content_hash = ""
		self.total_stalled = u32(self._bump(int(self.total_stalled)))
		self.total_pending = u32(_clamp(int(self.total_pending) - 1, 0, (1 << 32) - 1))
		self._release(key)
		return json.dumps({
			"ok": True,
			"verification_id": int(record.verification_id),
			"status": STATUS_STALLED,
			"reason": str(record.last_reason),
		})

	# ──────────────────────────────────────────────────────────────── views

	@gl.public.view
	def get_verification(self, verification_id: int) -> str:
		"""The full record. Returns `found: false` for an unknown id RATHER THAN
		RAISING - see _find. A view that raises reverts every contract that
		reads it, including payable ones, and takes their callers' value with
		it."""
		record = self._find(verification_id)
		if record is None:
			return json.dumps({"found": False, "verification_id": _as_int(verification_id, -1)})
		row = self._summary(record)
		row["found"] = True
		return json.dumps(row)

	@gl.public.view
	def get_verifications_by_user(self, github_username: str, offset: int, limit: int) -> str:
		"""Every verification for a username, newest first. Case-insensitive."""
		user = _normalize_username(github_username)
		# `is None` is wrong here: a DynArray-valued TreeMap answers an unknown
		# key with an EMPTY ARRAY on chain. _count_of and _page read correctly
		# under that AND under a stub that answers None.
		ids = self.by_user.get(user)
		rows = self._page(ids, offset, limit)
		return json.dumps({
			"github_username": user,
			"total": _count_of(ids),
			"returned": len(rows),
			"offset": _clamp(_as_int(offset, 0), 0, 1 << 30),
			"verifications": rows,
		})

	@gl.public.view
	def get_verifications_by_skill(self, skill: str, offset: int, limit: int) -> str:
		"""Every verification for a skill, newest first. Case-insensitive and
		whitespace-normalized, so "Jupyter  Notebook" finds the same bucket as
		"jupyter notebook"."""
		lang = _normalize_skill(skill)
		ids = self.by_skill.get(lang)
		rows = self._page(ids, offset, limit)
		return json.dumps({
			"skill": lang,
			"total": _count_of(ids),
			"returned": len(rows),
			"offset": _clamp(_as_int(offset, 0), 0, 1 << 30),
			"verifications": rows,
		})

	@gl.public.view
	def is_verified(self, github_username: str, skill: str, min_level: str) -> bool:
		"""Does this user meet or exceed `min_level` in this skill?

		THE COMPOSABILITY PRIMITIVE, and it NEVER RAISES for any input - not an
		unknown user, not a skill nobody has ever verified, not a garbage
		min_level. It answers False. A gate that reverts instead of answering
		cannot be used inside a payable method without taking the caller's
		value with it, which is precisely the bug that shipped in an earlier
		project. require_verified is the raising variant, for callers that want
		one.

		An unrecognised min_level is False rather than True: the failure mode of
		a typo must be "nobody passes", never "everybody does"."""
		want = _rank(min_level)
		if want < 0:
			return False
		record = self._latest_resolved_record(github_username, skill)
		if record is None:
			return False
		if not self._is_fresh(record):
			return False
		return _rank(str(record.level)) >= want

	@gl.public.view
	def require_verified(self, github_username: str, skill: str, min_level: str) -> str:
		"""REVERTS unless the user meets `min_level`. The assertion form.

		For callers that want the transaction to stop rather than to branch.
		Because it raises, it must never be reached from a payable method that
		has not wrapped it - SkillConsumer.claim_bounty demonstrates the wrap,
		and its comments explain why the wrap is not optional."""
		want = _rank(min_level)
		if want < 0:
			raise gl.vm.UserError("min_level must be one of " + ", ".join(LEVELS))
		record = self._latest_resolved_record(github_username, skill)
		if record is None:
			raise gl.vm.UserError(
				"no resolved verification for " + _normalize_username(github_username)
				+ " / " + _normalize_skill(skill),
			)
		if not self._is_fresh(record):
			raise gl.vm.UserError("verification " + str(int(record.verification_id)) + " is stale")
		have = _rank(str(record.level))
		if have < want:
			raise gl.vm.UserError(
				_normalize_username(github_username) + " is " + str(record.level)
				+ " in " + _normalize_skill(skill) + ", " + str(min_level) + " required",
			)
		row = self._summary(record)
		row["ok"] = True
		return json.dumps(row)

	@gl.public.view
	def get_stats(self) -> str:
		return json.dumps({
			"total_verifications": int(self.total_verifications),
			"resolved": int(self.total_resolved),
			"pending": int(self.total_pending),
			"stalled": int(self.total_stalled),
			"users_verified": int(self.distinct_users),
			"skills_verified": int(self.distinct_skills),
			"pairs_verified": int(self.distinct_pairs),
			"fees_collected": str(int(self.fees_collected)),
			"fees_withdrawn": str(int(self.fees_withdrawn)),
			"total_refunded": str(int(self.total_refunded)),
			"next_id": int(self.next_id),
		})

	@gl.public.view
	def get_config(self) -> str:
		return json.dumps({
			"owner": str(self.owner),
			"paused": bool(self.paused),
			"fee": str(int(self.fee)),
			"max_fee": str(MAX_FEE),
			"cooldown_seconds": int(self.cooldown),
			"resolve_window_seconds": int(self.resolve_window),
			"freshness_window_seconds": int(self.freshness_window),
			"levels": list(LEVELS),
			"axis_values": list(AXIS_VALUES),
			"statuses": [STATUS_PENDING, STATUS_RESOLVED, STATUS_STALLED],
			"thresholds": {
				"EXPERT": {"repos": EXPERT_REPOS, "bytes": EXPERT_BYTES},
				"PROFICIENT": {"repos": PROFICIENT_REPOS, "bytes": PROFICIENT_BYTES},
				"BEGINNER": {"repos": BEGINNER_REPOS, "bytes": 0},
			},
			"bytes_basis": BYTES_BASIS,
			"max_username_length": MAX_USERNAME,
			"max_skill_length": MAX_SKILL,
			"max_page": MAX_PAGE,
			"repos_scanned_per_verification": SEARCH_PAGE,
			"forks_counted": False,
			"source": GITHUB_SEARCH,
		})

	@gl.public.view
	def get_latest(self, github_username: str, skill: str) -> str:
		"""The verification is_verified and require_verified actually read.

		Exposed because a consumer that gets False from is_verified has no way
		to tell "never verified" from "verified BEGINNER" from "the record went
		stale", and those want three different messages in a user interface."""
		record = self._latest_resolved_record(github_username, skill)
		key_user = _normalize_username(github_username)
		key_skill = _normalize_skill(skill)
		if record is None:
			return json.dumps({
				"found": False,
				"github_username": key_user,
				"skill": key_skill,
				"pending_id": self._pending_id(key_user + "\x1f" + key_skill),
			})
		row = self._summary(record)
		row["found"] = True
		row["fresh"] = self._is_fresh(record)
		row["pending_id"] = self._pending_id(key_user + "\x1f" + key_skill)
		return json.dumps(row)

	def _latest_resolved_record(self, github_username: str, skill: str):
		# Ids are handed out from 1 (see __init__), so 0 unambiguously means "no
		# resolved verification for this pair" - which is exactly what a scalar
		# TreeMap answers for a key that was never written. `is None` would be
		# false for every unwritten key and send verification 0 to the lookup.
		found = _as_int(self.latest_resolved.get(self._pair_key(github_username, skill)), 0)
		if found <= 0:
			return None
		return self.verifications.get(u32(found))

	def _is_fresh(self, record) -> bool:
		"""Freshness, if the owner has configured any. The window ships at 0 -
		verifications never expire - because a skill does not decay and an
		expiry that nobody asked for silently breaks every consumer on the day
		it first fires."""
		window = int(self.freshness_window)
		if window <= 0:
			return True
		verified_at = int(record.verified_at)
		if verified_at <= 0:
			return False
		now = self._now()
		if now <= verified_at:
			return True
		return (now - verified_at) <= window

	# ──────────────────────────────────────────────────────────────── owner

	def _only_owner(self) -> None:
		if gl.message.sender_address != self.owner:
			raise gl.vm.UserError("owner only")

	@gl.public.write
	def set_fee(self, new_fee: int) -> str:
		"""Move the fee for FUTURE verifications. Every existing record carries
		its own fee_snapshot and is unreachable from here.

		Bounded by MAX_FEE so the owner cannot price the oracle out of
		existence, and rejected rather than clamped: silently accepting 500 GEN
		and storing 1 would leave the owner believing a fee is in force that is
		not."""
		self._only_owner()
		wanted = _as_int(new_fee, -1)
		if wanted < 0 or wanted > MAX_FEE:
			raise gl.vm.UserError("fee must be between 0 and " + str(MAX_FEE))
		self.fee = u128(wanted)
		return json.dumps({"ok": True, "fee": str(wanted)})

	@gl.public.write
	def set_cooldown(self, seconds: int) -> str:
		self._only_owner()
		wanted = _as_int(seconds, -1)
		if wanted < 0 or wanted > MAX_COOLDOWN:
			raise gl.vm.UserError("cooldown must be between 0 and " + str(MAX_COOLDOWN))
		self.cooldown = u64(wanted)
		return json.dumps({"ok": True, "cooldown_seconds": wanted})

	@gl.public.write
	def set_resolve_window(self, seconds: int) -> str:
		"""The DEFAULT window for verifications created afterwards. Records
		already in flight keep the window frozen onto them at request time."""
		self._only_owner()
		wanted = _as_int(seconds, -1)
		if wanted < MIN_RESOLVE_WINDOW or wanted > MAX_RESOLVE_WINDOW:
			raise gl.vm.UserError(
				"resolve window must be between " + str(MIN_RESOLVE_WINDOW) + " and " + str(MAX_RESOLVE_WINDOW),
			)
		self.resolve_window = u64(wanted)
		return json.dumps({"ok": True, "resolve_window_seconds": wanted})

	@gl.public.write
	def set_freshness_window(self, seconds: int) -> str:
		"""0 disables expiry entirely, which is the shipped default."""
		self._only_owner()
		wanted = _as_int(seconds, -1)
		if wanted < 0 or wanted > MAX_FRESHNESS:
			raise gl.vm.UserError("freshness window must be between 0 and " + str(MAX_FRESHNESS))
		self.freshness_window = u64(wanted)
		return json.dumps({"ok": True, "freshness_window_seconds": wanted})

	@gl.public.write
	def pause(self) -> str:
		"""Stop NEW verifications. Reads keep working, and so do resolve_pending
		and settle_stalled - a pause that could strand an in-flight record would
		be a way for the owner to make a username permanently unverifiable."""
		self._only_owner()
		self.paused = True
		return json.dumps({"ok": True, "paused": True})

	@gl.public.write
	def unpause(self) -> str:
		self._only_owner()
		self.paused = False
		return json.dumps({"ok": True, "paused": False})

	@gl.public.write
	def transfer_ownership(self, new_owner: str) -> str:
		self._only_owner()
		target = _as_text(new_owner).strip()
		if len(target) != 42 or not target.lower().startswith("0x"):
			raise gl.vm.UserError("new_owner must be a 0x-prefixed 20-byte address")
		if target.lower() == ZERO_ADDRESS:
			raise gl.vm.UserError("refusing to transfer ownership to the zero address")
		try:
			parsed = Address(target)
		except Exception:
			raise gl.vm.UserError("new_owner is not a valid address")
		self.owner = parsed
		return json.dumps({"ok": True, "owner": str(parsed)})

	@gl.public.write
	def withdraw_fees(self, amount: int) -> str:
		"""Withdraw collected fees, and NOTHING ELSE.

		The ceiling is `fees_collected - fees_withdrawn`, computed from the
		contract's own accounting rather than from its balance. That is the
		whole safety property: no user funds are ever held here (verify_skill
		refunds change in the same transaction), and this method cannot reach
		past fee income even if the balance is larger for some reason nobody
		anticipated."""
		self._only_owner()
		owed = _clamp(int(self.fees_collected) - int(self.fees_withdrawn), 0, (1 << 128) - 1)
		wanted = _as_int(amount, 0)
		if wanted <= 0:
			wanted = owed
		if wanted > owed:
			raise gl.vm.UserError("only " + str(owed) + " in fees is withdrawable")
		if wanted <= 0:
			raise gl.vm.UserError("no fees to withdraw")
		self.fees_withdrawn = u128(int(self.fees_withdrawn) + wanted)
		self._pay(self.owner, wanted)
		return json.dumps({"ok": True, "withdrawn": str(wanted), "remaining": str(owed - wanted)})
