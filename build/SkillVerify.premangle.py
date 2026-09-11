# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
from dataclasses import dataclass
import json
LEVEL_EXPERT = "EXPERT"
LEVEL_PROFICIENT = "PROFICIENT"
LEVEL_BEGINNER = "BEGINNER"
LEVEL_NONE = "NONE"
LEVELS = (LEVEL_NONE, LEVEL_BEGINNER, LEVEL_PROFICIENT, LEVEL_EXPERT)
EXPERT_REPOS = 5
EXPERT_BYTES = 1000
PROFICIENT_REPOS = 3
PROFICIENT_BYTES = 500
BEGINNER_REPOS = 1
AXIS_NO_SUCH_USER = "NO_SUCH_USER"
AXIS_UNAVAILABLE = "UNAVAILABLE"
AXIS_VALUES = (LEVEL_EXPERT, LEVEL_PROFICIENT, LEVEL_BEGINNER, LEVEL_NONE, AXIS_NO_SUCH_USER, AXIS_UNAVAILABLE)
STATUS_PENDING = "PENDING"
STATUS_RESOLVED = "RESOLVED"
STATUS_STALLED = "STALLED"
TERMINAL_STATUSES = (STATUS_RESOLVED, STATUS_STALLED)
MAX_USERNAME = 39
MAX_SKILL = 40
MAX_TOP_REPOS = 3
MAX_REPO_NAME = 100
SEARCH_PAGE = 100
MAX_ITEMS_SCANNED = 100
DEFAULT_FEE = 0
MAX_FEE = 10**18
DEFAULT_COOLDOWN = 300
MAX_COOLDOWN = 86400
DEFAULT_RESOLVE_WINDOW = 3600
MIN_RESOLVE_WINDOW = 60
MAX_RESOLVE_WINDOW = 30 * 86400
DEFAULT_FRESHNESS = 0
MAX_FRESHNESS = 365 * 86400
MAX_PAGE = 50
MAX_ATTEMPTS = 1000
BYTES_BASIS = "github_repo_size_kb"
GITHUB_SEARCH = "https://api.github.com/search/repositories"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
UNRESERVED = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
HEX = "0123456789ABCDEF"
def _as_int(value, fallback: int) -> int:
 try:
  if isinstance(value, bool):
   return fallback
  return int(value)
 except Exception:
  return fallback
def _as_text(value) -> str:
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
 if not isinstance(text, str):
  return ""
 if text == "":
  return ""
 h = 0xCBF29CE484222325
 for byte in text.encode("utf-8"):
  h = ((h ^ byte) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
 return "%016x" % h
def _content_hash(username: str, skill: str, level: str, repo_count: int, total_bytes: int) -> str:
 parts = [
 _normalize_username(username),
 _normalize_skill(skill),
 _as_text(level),
 str(_as_int(repo_count, 0)),
 str(_as_int(total_bytes, 0)),
 ]
 return _fnv("\x1f".join(parts))
def _normalize_username(value) -> str:
 text = _as_text(value).strip()
 return text.lower()[:MAX_USERNAME]
def _normalize_skill(value) -> str:
 return " ".join(_as_text(value).split()).lower()[:MAX_SKILL]
def _display_skill(value) -> str:
 return " ".join(_as_text(value).split())[:MAX_SKILL]
def _normalize_address(value) -> str:
 return _as_text(value).strip().lower()
def _is_zero_address(value) -> bool:
 text = _normalize_address(value)
 if text == "" or text == "none":
  return True
 if text.startswith("0x"):
  text = text[2:]
 return text.strip("0") == ""
def _username_problem(value) -> str:
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
 user = _pct(_normalize_username(username))
 lang = _pct(_normalize_skill(skill))
 q = "user:" + user + "%20language:%22" + lang + "%22"
 return GITHUB_SEARCH + "?per_page=" + str(SEARCH_PAGE) + "&sort=updated&q=" + q
def _rank(level) -> int:
 text = _as_text(level)
 for i in range(len(LEVELS)):
  if LEVELS[i] == text:
   return i
 return -1
def _level_for(repo_count: int, total_bytes: int) -> str:
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
 if bucket is None:
  return 0
 try:
  return len(bucket)
 except Exception:
  return 0
def _top_list(raw) -> list:
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
 if not isinstance(result, dict):
  return AXIS_UNAVAILABLE
 axis = _as_text(result.get("axis"))
 if axis in AXIS_VALUES:
  return axis
 return AXIS_UNAVAILABLE
def _compare_key(result) -> str:
 axis = _axis_of(result)
 if _rank(axis) < 0:
  return axis
 if not isinstance(result, dict):
  return AXIS_UNAVAILABLE
 repos = _as_int(result.get("repo_count"), -1)
 size = _as_int(result.get("total_bytes"), -1)
 return axis + "\x1f" + str(repos) + "\x1f" + str(size)
def _run_evaluation(username: str, skill: str) -> dict:
 user = str(username)
 lang = str(skill)
 def leader_fn() -> dict:
  return _evaluate(user, lang)
 def validator_fn(leader_result: gl.vm.Result) -> bool:
  if not isinstance(leader_result, gl.vm.Return):
   leader_fn()
   return False
  mine = _compare_key(leader_fn())
  theirs = _compare_key(leader_result.calldata)
  return mine == theirs
 outcome = gl.vm.run_nondet(leader_fn, validator_fn)
 if not isinstance(outcome, dict):
  return {"axis": AXIS_UNAVAILABLE, "status": 0, "reason": "nondet returned no document"}
 return outcome
@allow_storage
@dataclass
class Verification:
 verification_id: u32
 github_username: str
 username_display: str
 skill: str
 skill_display: str
 status: str
 level: str
 repo_count: u32
 total_bytes: u128
 index_count: u32
 top_repos: str
 content_hash: str
 verified_at: u64
 verified_by: Address
 requested_at: u64
 resolve_window: u64
 fee_paid: u128
 fee_snapshot: u128
 bytes_basis: str
 attempts: u32
 user_found: bool
 incomplete_index: bool
 last_reason: str
 http_status: u32
@gl.evm.contract_interface
class _Payee:
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
 by_pair: TreeMap[str, DynArray[u32]]
 by_user: TreeMap[str, DynArray[u32]]
 by_skill: TreeMap[str, DynArray[u32]]
 latest_resolved: TreeMap[str, u32]
 inflight: TreeMap[str, u32]
 identities: TreeMap[str, Address]
 identity_at: TreeMap[str, u64]
 last_request_at: TreeMap[Address, u64]
 fee: u128
 cooldown: u64
 resolve_window: u64
 freshness_window: u64
 total_verifications: u32
 distinct_users: u32
 distinct_skills: u32
 distinct_pairs: u32
 total_resolved: u32
 total_stalled: u32
 total_pending: u32
 total_identities: u32
 fees_collected: u128
 fees_withdrawn: u128
 total_refunded: u128
 def __init__(self, fee: int = DEFAULT_FEE):
  self.owner = gl.message.sender_address
  self.paused = False
  self.next_id = u32(1)
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
  self.total_identities = u32(0)
  self.fees_collected = u128(0)
  self.fees_withdrawn = u128(0)
  self.total_refunded = u128(0)
 def _now(self) -> int:
  return _epoch_from_iso(gl.message_raw.get("datetime", ""))
 def _pay(self, to: Address, amount: int) -> None:
  if amount <= 0:
   return
  _Payee(Address(str(to))).emit_transfer(value=u256(int(amount)))
 def _reject(self, sender: Address, value: int, reason: str) -> str:
  if value > 0:
   self._pay(sender, value)
   self.total_refunded = u128(_clamp(int(self.total_refunded) + value, 0, (1 << 128) - 1))
  return json.dumps({"ok": False, "reason": reason, "refunded": str(value)})
 def _identity_owner(self, username: str) -> str:
  owner = self.identities.get(username)
  if owner is None:
   return ""
  text = _normalize_address(str(owner))
  if _is_zero_address(text):
   return ""
  return text
 def _identity_doc(self, username: str) -> dict:
  owner = self._identity_owner(username)
  return {
  "github_username": username,
  "registered": owner != "",
  "identity_owner": owner,
  "identity_registered_at": _as_int(self.identity_at.get(username), 0) if owner else 0,
  }
 def _pair_key(self, username: str, skill: str) -> str:
  return _normalize_username(username) + "\x1f" + _normalize_skill(skill)
 def _find(self, verification_id: int):
  return self.verifications.get(u32(_clamp(_as_int(verification_id, -1), 0, (1 << 32) - 1)))
 def _mutable(self, record) -> bool:
  if record is None:
   return False
  return str(record.status) not in TERMINAL_STATUSES
 def _index(self, key: str, table, verification_id: int) -> bool:
  bucket = table.get_or_insert_default(key)
  first = len(bucket) == 0
  bucket.append(u32(verification_id))
  return first
 def _bump(self, field_value: int) -> int:
  return _clamp(field_value + 1, 0, (1 << 32) - 1)
 def _summary(self, record) -> dict:
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
  "identity_owner": self._identity_owner(str(record.github_username)),
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
  axis = _axis_of(outcome)
  status_code = _clamp(_as_int(outcome.get("status"), 0), 0, (1 << 32) - 1)
  reason = _as_text(outcome.get("reason"))[:200]
  if axis == AXIS_UNAVAILABLE:
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
   recomputed = _level_for(repo_count, total_bytes)
   if recomputed != level:
    record.attempts = u32(_clamp(int(record.attempts) + 1, 0, MAX_ATTEMPTS))
    record.last_reason = (
    "incoherent result: level " + level + " with " + str(repo_count)
    + " repos and " + str(total_bytes) + " bytes, which is " + recomputed
    )[:200]
    record.http_status = u32(status_code)
    return {"resolved": False, "axis": AXIS_UNAVAILABLE,
    "incoherent": True, "reason": record.last_reason}
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
  self.inflight[key] = u32(0)
 def _pending_id(self, key: str) -> int:
  return _as_int(self.inflight.get(key), 0) - 1
 def _page(self, ids, offset: int, limit: int) -> list:
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
 @gl.public.write
 def register_identity(self, github_username: str) -> str:
  sender = gl.message.sender_address
  if self.paused:
   return json.dumps({"ok": False, "reason": "contract is paused"})
  problem = _username_problem(github_username)
  if problem:
   return json.dumps({"ok": False, "reason": problem})
  user = _normalize_username(github_username)
  held = self._identity_owner(user)
  if held != "":
   if held == _normalize_address(str(sender)):
    return json.dumps({
    "ok": True, "github_username": user, "identity_owner": held,
    "already_registered": True,
    "registered_at": _as_int(self.identity_at.get(user), 0),
    })
   return json.dumps({
   "ok": False, "github_username": user, "identity_owner": held,
   "reason": user + " is already registered to " + held
   + " and a registration can never be moved",
   })
  self.identities[user] = sender
  self.identity_at[user] = u64(_clamp(self._now(), 0, (1 << 64) - 1))
  self.total_identities = u32(self._bump(int(self.total_identities)))
  return json.dumps({
  "ok": True,
  "github_username": user,
  "identity_owner": _normalize_address(str(sender)),
  "already_registered": False,
  "registered_at": _as_int(self.identity_at.get(user), 0),
  })
 @gl.public.write.payable
 def verify_skill(self, github_username: str, skill: str) -> str:
  sender = gl.message.sender_address
  value = _as_int(gl.message.value, 0)
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
  outcome = _run_evaluation(_normalize_username(github_username), _normalize_skill(skill))
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
  key = self._pair_key(str(record.github_username), str(record.skill))
  record.status = STATUS_STALLED
  record.level = ""
  record.last_reason = "unresolved after " + str(int(record.resolve_window)) + "s"
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
 @gl.public.view
 def get_verification(self, verification_id: int) -> str:
  record = self._find(verification_id)
  if record is None:
   return json.dumps({"found": False, "verification_id": _as_int(verification_id, -1)})
  row = self._summary(record)
  row["found"] = True
  return json.dumps(row)
 @gl.public.view
 def get_verifications_by_user(self, github_username: str, offset: int, limit: int) -> str:
  user = _normalize_username(github_username)
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
 def get_identity(self, github_username: str) -> str:
  return json.dumps(self._identity_doc(_normalize_username(github_username)))
 @gl.public.view
 def owns_identity(self, github_username: str, claimant: str) -> bool:
  owner = self._identity_owner(_normalize_username(github_username))
  if owner == "":
   return False
  wanted = _normalize_address(claimant)
  if _is_zero_address(wanted):
   return False
  return owner == wanted
 @gl.public.view
 def is_verified_identity(self, github_username: str, skill: str, min_level: str, claimant: str) -> bool:
  if not self.owns_identity(github_username, claimant):
   return False
  return self.is_verified(github_username, skill, min_level)
 @gl.public.view
 def get_stats(self) -> str:
  return json.dumps({
  "total_verifications": int(self.total_verifications),
  "resolved": int(self.total_resolved),
  "pending": int(self.total_pending),
  "stalled": int(self.total_stalled),
  "identities_registered": int(self.total_identities),
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
  "identity_binding": "register_identity",
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
  record = self._latest_resolved_record(github_username, skill)
  key_user = _normalize_username(github_username)
  key_skill = _normalize_skill(skill)
  if record is None:
   return json.dumps({
   "found": False,
   "github_username": key_user,
   "skill": key_skill,
   "identity_owner": self._identity_owner(key_user),
   "pending_id": self._pending_id(key_user + "\x1f" + key_skill),
   })
  row = self._summary(record)
  row["found"] = True
  row["fresh"] = self._is_fresh(record)
  row["pending_id"] = self._pending_id(key_user + "\x1f" + key_skill)
  return json.dumps(row)
 def _latest_resolved_record(self, github_username: str, skill: str):
  found = _as_int(self.latest_resolved.get(self._pair_key(github_username, skill)), 0)
  if found <= 0:
   return None
  return self.verifications.get(u32(found))
 def _is_fresh(self, record) -> bool:
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
 def _only_owner(self) -> None:
  if gl.message.sender_address != self.owner:
   raise gl.vm.UserError("owner only")
 @gl.public.write
 def set_fee(self, new_fee: int) -> str:
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
  self._only_owner()
  wanted = _as_int(seconds, -1)
  if wanted < 0 or wanted > MAX_FRESHNESS:
   raise gl.vm.UserError("freshness window must be between 0 and " + str(MAX_FRESHNESS))
  self.freshness_window = u64(wanted)
  return json.dumps({"ok": True, "freshness_window_seconds": wanted})
 @gl.public.write
 def pause(self) -> str:
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
