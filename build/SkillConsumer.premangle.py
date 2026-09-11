# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
from dataclasses import dataclass
import json
LEVEL_EXPERT = "EXPERT"
LEVEL_PROFICIENT = "PROFICIENT"
LEVEL_BEGINNER = "BEGINNER"
LEVEL_NONE = "NONE"
LEVELS = (LEVEL_NONE, LEVEL_BEGINNER, LEVEL_PROFICIENT, LEVEL_EXPERT)
STATUS_OPEN = "OPEN"
STATUS_CLAIMED = "CLAIMED"
STATUS_WITHDRAWN = "WITHDRAWN"
TERMINAL_STATUSES = (STATUS_CLAIMED, STATUS_WITHDRAWN)
MIN_REWARD = 10 ** 15
MAX_REWARD = 100 * 10 ** 18
MAX_BOUNTIES = 2000
MAX_PAGE = 50
MAX_SKILL = 40
MAX_USERNAME = 39
MAX_TITLE = 120
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
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
def _normalize_username(value) -> str:
 return _as_text(value).strip().lower()[:MAX_USERNAME]
def _normalize_skill(value) -> str:
 return " ".join(_as_text(value).split()).lower()[:MAX_SKILL]
def _normalize_address(value) -> str:
 return _as_text(value).strip().lower()
def _is_zero_address(value) -> bool:
 text = _normalize_address(value)
 if text == "" or text == "none":
  return True
 if text.startswith("0x"):
  text = text[2:]
 return text.strip("0") == ""
def _rank(level) -> int:
 text = _as_text(level)
 for i in range(len(LEVELS)):
  if LEVELS[i] == text:
   return i
 return -1
def _as_json(value) -> dict:
 if isinstance(value, dict):
  return value
 try:
  parsed = json.loads(_as_text(value))
 except Exception:
  return {}
 if isinstance(parsed, dict):
  return parsed
 return {}
@gl.evm.contract_interface
class _Payee:
 class View:
  pass
 class Write:
  pass
@allow_storage
@dataclass
class Bounty:
 bounty_id: u32
 poster: Address
 title: str
 skill: str
 skill_display: str
 min_level: str
 reward: u128
 status: str
 created_at: u64
 claimed_at: u64
 claimant: Address
 claimed_username: str
 claimed_level: str
 verification_id: u32
 content_hash: str
class SkillConsumer(gl.Contract):
 owner: Address
 oracle: Address
 bounties: TreeMap[u32, Bounty]
 bounty_ids: DynArray[u32]
 next_id: u32
 by_skill: TreeMap[str, DynArray[u32]]
 by_poster: TreeMap[Address, DynArray[u32]]
 total_posted: u128
 total_paid: u128
 total_withdrawn: u128
 total_refunded: u128
 open_liability: u128
 def __init__(self, oracle: str):
  self.owner = gl.message.sender_address
  self.oracle = Address(_as_text(oracle))
  self.next_id = u32(1)
  self.total_posted = u128(0)
  self.total_paid = u128(0)
  self.total_withdrawn = u128(0)
  self.total_refunded = u128(0)
  self.open_liability = u128(0)
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
 def _level_of(self, github_username: str, skill: str) -> dict:
  try:
   handle = gl.get_contract_at(self.oracle)
   raw = handle.view().get_latest(
   _normalize_username(github_username), _normalize_skill(skill),
   )
  except Exception:
   return {"found": False, "level": "", "rank": -1, "identity_owner": "",
   "oracle_down": True, "reason": "oracle unreachable"}
  document = _as_json(raw)
  owner = _normalize_address(document.get("identity_owner"))
  if _is_zero_address(owner):
   owner = ""
  if not bool(document.get("found", False)):
   return {"found": False, "level": "", "rank": -1, "identity_owner": owner,
   "reason": "no resolved verification"}
  if not bool(document.get("fresh", True)):
   return {"found": False, "level": _as_text(document.get("level")), "rank": -1,
   "identity_owner": owner, "reason": "verification is stale"}
  level = _as_text(document.get("level"))
  return {
  "found": True,
  "level": level,
  "rank": _rank(level),
  "identity_owner": owner,
  "verified_by": _normalize_address(document.get("verified_by")),
  "verification_id": _as_int(document.get("verification_id"), 0),
  "content_hash": _as_text(document.get("content_hash")),
  "repo_count": _as_int(document.get("repo_count"), 0),
  "reason": "",
  }
 def _claim_problem(self, bounty, user: str, claimant: str, found: dict) -> dict:
  if bool(found.get("oracle_down", False)):
   return {
   "ok": False,
   "reason": user + " cannot be checked: " + _as_text(found.get("reason")),
   "claimant": claimant,
   }
  owner = _as_text(found.get("identity_owner"))
  if owner == "":
   return {
   "ok": False,
   "reason": user + " is not bound to any wallet: call register_identity(\""
   + user + "\") on the oracle from the wallet that owns it, then claim",
   "identity_owner": "",
   "claimant": claimant,
   }
  if owner != claimant or _is_zero_address(claimant):
   return {
   "ok": False,
   "reason": user + " is registered to " + owner
   + " and only that wallet may claim against it",
   "identity_owner": owner,
   "claimant": claimant,
   }
  if not bool(found.get("found", False)):
   return {
   "ok": False,
   "reason": user + " has no usable verification for " + str(bounty.skill)
   + ": " + _as_text(found.get("reason")),
   "required": str(bounty.min_level),
   }
  want = _rank(str(bounty.min_level))
  have = _as_int(found.get("rank"), -1)
  if have < want:
   return {
   "ok": False,
   "reason": user + " is " + _as_text(found.get("level")) + ", "
   + str(bounty.min_level) + " required",
   "level": _as_text(found.get("level")),
   "required": str(bounty.min_level),
   }
  return {}
 def _find(self, bounty_id: int):
  return self.bounties.get(u32(_clamp(_as_int(bounty_id, -1), 0, (1 << 32) - 1)))
 def _mutable(self, bounty) -> bool:
  if bounty is None:
   return False
  return str(bounty.status) not in TERMINAL_STATUSES
 def _summary(self, bounty) -> dict:
  return {
  "bounty_id": int(bounty.bounty_id),
  "poster": str(bounty.poster),
  "title": str(bounty.title),
  "skill": str(bounty.skill),
  "skill_display": str(bounty.skill_display),
  "min_level": str(bounty.min_level),
  "min_level_rank": _rank(str(bounty.min_level)),
  "reward": str(int(bounty.reward)),
  "status": str(bounty.status),
  "created_at": int(bounty.created_at),
  "claimed_at": int(bounty.claimed_at),
  "claimant": str(bounty.claimant),
  "claimed_username": str(bounty.claimed_username),
  "claimed_level": str(bounty.claimed_level),
  "verification_id": int(bounty.verification_id),
  "content_hash": str(bounty.content_hash),
  }
 def _page(self, ids, offset: int, limit: int) -> list:
  if ids is None:
   return []
  start = _clamp(_as_int(offset, 0), 0, 1 << 30)
  count = _as_int(limit, MAX_PAGE)
  if count <= 0 or count > MAX_PAGE:
   count = MAX_PAGE
  rows = []
  i = len(ids) - 1 - start
  while i >= 0 and len(rows) < count:
   bounty = self.bounties.get(u32(int(ids[i])))
   if bounty is not None:
    rows.append(self._summary(bounty))
   i -= 1
  return rows
 @gl.public.view
 def require_skill(self, github_username: str, skill: str, min_level: str) -> str:
  want = _rank(min_level)
  if want < 0:
   raise gl.vm.UserError("min_level must be one of " + ", ".join(LEVELS))
  found = self._level_of(github_username, skill)
  if not found["found"]:
   raise gl.vm.UserError(
   _normalize_username(github_username) + " has no usable verification for "
   + _normalize_skill(skill) + ": " + str(found["reason"]),
   )
  if int(found["rank"]) < want:
   raise gl.vm.UserError(
   _normalize_username(github_username) + " is " + str(found["level"])
   + " in " + _normalize_skill(skill) + ", " + str(min_level) + " required",
   )
  return json.dumps({
  "ok": True,
  "github_username": _normalize_username(github_username),
  "skill": _normalize_skill(skill),
  "level": str(found["level"]),
  "required": _as_text(min_level),
  "verification_id": int(found.get("verification_id", 0)),
  "content_hash": str(found.get("content_hash", "")),
  })
 @gl.public.view
 def check_skill(self, github_username: str, skill: str, min_level: str) -> bool:
  want = _rank(min_level)
  if want < 0:
   return False
  found = self._level_of(github_username, skill)
  if not found["found"]:
   return False
  return int(found["rank"]) >= want
 @gl.public.view
 def get_skill_report(self, github_username: str, skill: str) -> str:
  found = self._level_of(github_username, skill)
  return json.dumps({
  "github_username": _normalize_username(github_username),
  "skill": _normalize_skill(skill),
  "found": bool(found["found"]),
  "level": str(found["level"]),
  "rank": int(found["rank"]),
  "verification_id": int(found.get("verification_id", 0)),
  "content_hash": str(found.get("content_hash", "")),
  "identity_owner": str(found.get("identity_owner", "")),
  "verified_by": str(found.get("verified_by", "")),
  "reason": str(found.get("reason", "")),
  "oracle": str(self.oracle),
  })
 @gl.public.write.payable
 def post_bounty(self, title: str, skill: str, min_level: str) -> str:
  sender = gl.message.sender_address
  value = _as_int(gl.message.value, 0)
  if value < MIN_REWARD:
   return self._reject(sender, value, "reward must be at least " + str(MIN_REWARD))
  if value > MAX_REWARD:
   return self._reject(sender, value, "reward must be at most " + str(MAX_REWARD))
  clean_title = " ".join(_as_text(title).split())[:MAX_TITLE]
  if clean_title == "":
   return self._reject(sender, value, "title is empty")
  clean_skill = _normalize_skill(skill)
  if clean_skill == "":
   return self._reject(sender, value, "skill is empty")
  want = _rank(min_level)
  if want < 0:
   return self._reject(sender, value, "min_level must be one of " + ", ".join(LEVELS))
  if want == 0:
   return self._reject(sender, value, "min_level NONE would let anybody claim; use BEGINNER or higher")
  if len(self.bounty_ids) >= MAX_BOUNTIES:
   return self._reject(sender, value, "bounty book is full")
  if int(self.next_id) >= (1 << 32) - 1:
   return self._reject(sender, value, "bounty id space is exhausted")
  bounty_id = int(self.next_id)
  self.next_id = u32(bounty_id + 1)
  bounty = self.bounties.get_or_insert_default(u32(bounty_id))
  bounty.bounty_id = u32(bounty_id)
  bounty.poster = sender
  bounty.title = clean_title
  bounty.skill = clean_skill
  bounty.skill_display = " ".join(_as_text(skill).split())[:MAX_SKILL]
  bounty.min_level = _as_text(min_level)
  bounty.reward = u128(value)
  bounty.status = STATUS_OPEN
  bounty.created_at = u64(_clamp(self._now(), 0, (1 << 64) - 1))
  bounty.claimed_at = u64(0)
  bounty.claimant = Address(ZERO_ADDRESS)
  bounty.claimed_username = ""
  bounty.claimed_level = ""
  bounty.verification_id = u32(0)
  bounty.content_hash = ""
  self.bounty_ids.append(u32(bounty_id))
  self.by_skill.get_or_insert_default(clean_skill).append(u32(bounty_id))
  self.by_poster.get_or_insert_default(sender).append(u32(bounty_id))
  self.total_posted = u128(_clamp(int(self.total_posted) + value, 0, (1 << 128) - 1))
  self.open_liability = u128(_clamp(int(self.open_liability) + value, 0, (1 << 128) - 1))
  return json.dumps({
  "ok": True,
  "bounty_id": bounty_id,
  "reward": str(value),
  "skill": clean_skill,
  "min_level": _as_text(min_level),
  })
 @gl.public.write
 def claim_bounty(self, bounty_id: int, github_username: str) -> str:
  bounty = self._find(bounty_id)
  if bounty is None:
   return json.dumps({"ok": False, "reason": "unknown bounty_id"})
  if not self._mutable(bounty):
   return json.dumps({
   "ok": False,
   "reason": "bounty is " + str(bounty.status) + " and can never change",
   "status": str(bounty.status),
   })
  user = _normalize_username(github_username)
  if user == "":
   return json.dumps({"ok": False, "reason": "github_username is empty"})
  claimant = _normalize_address(str(gl.message.sender_address))
  found = self._level_of(user, str(bounty.skill))
  problem = self._claim_problem(bounty, user, claimant, found)
  if problem:
   return json.dumps(problem)
  reward = int(bounty.reward)
  bounty.status = STATUS_CLAIMED
  bounty.claimant = gl.message.sender_address
  bounty.claimed_username = user
  bounty.claimed_level = str(found["level"])
  bounty.verification_id = u32(_clamp(_as_int(found.get("verification_id"), 0), 0, (1 << 32) - 1))
  bounty.content_hash = _as_text(found.get("content_hash"))
  bounty.claimed_at = u64(_clamp(self._now(), 0, (1 << 64) - 1))
  self.total_paid = u128(_clamp(int(self.total_paid) + reward, 0, (1 << 128) - 1))
  self.open_liability = u128(_clamp(int(self.open_liability) - reward, 0, (1 << 128) - 1))
  self._pay(gl.message.sender_address, reward)
  return json.dumps({
  "ok": True,
  "bounty_id": int(bounty.bounty_id),
  "paid": str(reward),
  "to": str(bounty.claimant),
  "github_username": user,
  "identity_owner": claimant,
  "level": str(found["level"]),
  "verification_id": int(bounty.verification_id),
  "content_hash": str(bounty.content_hash),
  })
 @gl.public.write
 def withdraw_bounty(self, bounty_id: int) -> str:
  bounty = self._find(bounty_id)
  if bounty is None:
   return json.dumps({"ok": False, "reason": "unknown bounty_id"})
  if not self._mutable(bounty):
   return json.dumps({
   "ok": False,
   "reason": "bounty is " + str(bounty.status) + " and can never change",
   "status": str(bounty.status),
   })
  if gl.message.sender_address != bounty.poster:
   return json.dumps({"ok": False, "reason": "only the poster may withdraw this bounty"})
  reward = int(bounty.reward)
  bounty.status = STATUS_WITHDRAWN
  bounty.claimed_at = u64(_clamp(self._now(), 0, (1 << 64) - 1))
  self.total_withdrawn = u128(_clamp(int(self.total_withdrawn) + reward, 0, (1 << 128) - 1))
  self.open_liability = u128(_clamp(int(self.open_liability) - reward, 0, (1 << 128) - 1))
  self._pay(bounty.poster, reward)
  return json.dumps({"ok": True, "bounty_id": int(bounty.bounty_id), "refunded": str(reward)})
 @gl.public.view
 def get_bounty(self, bounty_id: int) -> str:
  bounty = self._find(bounty_id)
  if bounty is None:
   return json.dumps({"found": False, "bounty_id": _as_int(bounty_id, -1)})
  row = self._summary(bounty)
  row["found"] = True
  return json.dumps(row)
 @gl.public.view
 def can_claim(self, bounty_id: int, github_username: str, claimant: str) -> str:
  bounty = self._find(bounty_id)
  if bounty is None:
   return json.dumps({"ok": False, "reason": "unknown bounty_id"})
  if not self._mutable(bounty):
   return json.dumps({
   "ok": False,
   "reason": "bounty is " + str(bounty.status) + " and can never change",
   "status": str(bounty.status),
   })
  user = _normalize_username(github_username)
  if user == "":
   return json.dumps({"ok": False, "reason": "github_username is empty"})
  who = _normalize_address(claimant)
  found = self._level_of(user, str(bounty.skill))
  problem = self._claim_problem(bounty, user, who, found)
  if problem:
   return json.dumps(problem)
  return json.dumps({
  "ok": True,
  "bounty_id": int(bounty.bounty_id),
  "github_username": user,
  "identity_owner": who,
  "level": _as_text(found.get("level")),
  "required": str(bounty.min_level),
  "reward": str(int(bounty.reward)),
  })
 @gl.public.view
 def get_bounties(self, offset: int, limit: int) -> str:
  rows = self._page(self.bounty_ids, offset, limit)
  return json.dumps({"total": len(self.bounty_ids), "returned": len(rows), "bounties": rows})
 @gl.public.view
 def get_bounties_by_skill(self, skill: str, offset: int, limit: int) -> str:
  ids = self.by_skill.get(_normalize_skill(skill))
  rows = self._page(ids, offset, limit)
  total = 0 if ids is None else len(ids)
  return json.dumps({"skill": _normalize_skill(skill), "total": total, "returned": len(rows), "bounties": rows})
 @gl.public.view
 def get_terms(self) -> str:
  return json.dumps({
  "owner": str(self.owner),
  "oracle": str(self.oracle),
  "levels": list(LEVELS),
  "statuses": [STATUS_OPEN, STATUS_CLAIMED, STATUS_WITHDRAWN],
  "claims_are_identity_bound": True,
  "min_reward": str(MIN_REWARD),
  "max_reward": str(MAX_REWARD),
  "max_bounties": MAX_BOUNTIES,
  "max_page": MAX_PAGE,
  "total_posted": str(int(self.total_posted)),
  "total_paid": str(int(self.total_paid)),
  "total_withdrawn": str(int(self.total_withdrawn)),
  "total_refunded": str(int(self.total_refunded)),
  "open_liability": str(int(self.open_liability)),
  "bounties": len(self.bounty_ids),
  })
 @gl.public.view
 def get_oracle_config(self) -> str:
  try:
   handle = gl.get_contract_at(self.oracle)
   return _as_text(handle.view().get_config())
  except Exception:
   return json.dumps({"error": "oracle unreachable", "oracle": str(self.oracle)})
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
