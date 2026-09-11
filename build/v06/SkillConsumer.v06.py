# v0.3.0
# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng" }
import genlayer as gl
from genlayer import *
from dataclasses import dataclass
import json
av = "EXPERT"
ag = "PROFICIENT"
ao = "BEGINNER"
aD = "NONE"
X = (aD, ao, ag, av)
ae = "OPEN"
H = "CLAIMED"
B = "WITHDRAWN"
ad = (H, B)
S = 10 ** 15
T = 100 * 10 ** 18
Y = 2000
U = 50
ap = 40
aw = 39
aF = 120
ax = "0x0000000000000000000000000000000000000000"
def x(value, ay: int) -> int:
 try:
  if isinstance(value, bool):
   return ay
  return int(value)
 except Exception:
  return ay
def f(value) -> str:
 if value is None:
  return ""
 if isinstance(value, str):
  return value
 try:
  return str(value)
 except Exception:
  return ""
def q(value: int, aW: int, aP: int) -> int:
 if value < aW:
  return aW
 if value > aP:
  return aP
 return value
def h(value) -> str:
 return f(value).strip().lower()[:aw]
def j(value) -> str:
 return " ".join(f(value).split()).lower()[:ap]
def o(value) -> str:
 return f(value).strip().lower()
def O(value) -> bool:
 Z = o(value)
 if Z == "" or Z == "none":
  return True
 if Z.startswith("0x"):
  Z = Z[2:]
 return Z.strip("0") == ""
def ab(aq) -> int:
 Z = f(aq)
 for i in range(len(X)):
  if X[i] == Z:
   return i
 return -1
def aL(value) -> dict:
 if isinstance(value, dict):
  return value
 try:
  aG = json.loads(f(value))
 except Exception:
  return {}
 if isinstance(aG, dict):
  return aG
 return {}
@gl.evm.contract_interface
class _Payee:
 class View:
  pass
 class Write:
  pass
@gl.storage.allow
@dataclass
class Bounty:
 c: u32
 ak: Address
 ar: str
 n: str
 W: str
 g: str
 p: u128
 v: str
 al: u64
 M: u64
 k: Address
 C: str
 L: str
 t: u32
 E: str
class SkillConsumer(gl.contract.Contract):
 z: Address
 J: Address
 ah: gl.storage.TreeMap[u32, Bounty]
 F: gl.storage.DynArray[u32]
 ac: u32
 az: gl.storage.TreeMap[str, gl.storage.DynArray[u32]]
 aH: gl.storage.TreeMap[Address, gl.storage.DynArray[u32]]
 G: u128
 N: u128
 u: u128
 A: u128
 l: u128
 def __init__(self, J: str):
  self.z = gl.message.sender_address
  self.J = Address(f(J))
  self.ac = u32(1)
  self.G = u128(0)
  self.N = u128(0)
  self.u = u128(0)
  self.A = u128(0)
  self.l = u128(0)
 def aM(self) -> int:
  return am(gl.message.raw.get("datetime", ""))
 def aN(self, to: Address, aI: int) -> None:
  if aI <= 0:
   return
  _Payee(Address(str(to))).emit_transfer(value=u256(int(aI)))
 def D(self, s: Address, value: int, aQ: str) -> str:
  if value > 0:
   self.aN(s, value)
   self.A = u128(q(int(self.A) + value, 0, (1 << 128) - 1))
  return json.dumps({"ok": False, "reason": aQ, "refunded": str(value)})
 def K(self, b: str, n: str) -> dict:
  try:
   aA = gl.contract.get_at(self.J)
   bd = aA.view().get_latest(
   h(b), j(n),
   )
  except Exception:
   return {"found": False, "level": "", "rank": -1, "identity_owner": "",
   "oracle_down": True, "reason": "oracle unreachable"}
  r = aL(bd)
  z = o(r.get("identity_owner"))
  if O(z):
   z = ""
  if not bool(r.get("found", False)):
   return {"found": False, "level": "", "rank": -1, "identity_owner": z,
   "reason": "no resolved verification"}
  if not bool(r.get("fresh", True)):
   return {"found": False, "level": f(r.get("level")), "rank": -1,
   "identity_owner": z, "reason": "verification is stale"}
  aq = f(r.get("level"))
  return {
  "found": True,
  "level": aq,
  "rank": ab(aq),
  "identity_owner": z,
  "verified_by": o(r.get("verified_by")),
  "verification_id": x(r.get("verification_id"), 0),
  "content_hash": f(r.get("content_hash")),
  "repo_count": x(r.get("repo_count"), 0),
  "reason": "",
  }
 def Q(self, a, w: str, k: str, e: dict) -> dict:
  if bool(e.get("oracle_down", False)):
   return {
   "ok": False,
   "reason": w + " cannot be checked: " + f(e.get("reason")),
   "claimant": k,
   }
  z = f(e.get("identity_owner"))
  if z == "":
   return {
   "ok": False,
   "reason": w + " is not bound to any wallet: call register_identity(\""
   + w + "\") on the oracle from the wallet that owns it, then claim",
   "identity_owner": "",
   "claimant": k,
   }
  if z != k or O(k):
   return {
   "ok": False,
   "reason": w + " is registered to " + z
   + " and only that wallet may claim against it",
   "identity_owner": z,
   "claimant": k,
   }
  if not bool(e.get("found", False)):
   return {
   "ok": False,
   "reason": w + " has no usable verification for " + str(a.n)
   + ": " + f(e.get("reason")),
   "required": str(a.g),
   }
  P = ab(str(a.g))
  ba = x(e.get("rank"), -1)
  if ba < P:
   return {
   "ok": False,
   "reason": w + " is " + f(e.get("level")) + ", "
   + str(a.g) + " required",
   "level": f(e.get("level")),
   "required": str(a.g),
   }
  return {}
 def at(self, c: int):
  return self.ah.get(u32(q(x(c, -1), 0, (1 << 32) - 1)))
 def ai(self, a) -> bool:
  if a is None:
   return False
  return str(a.v) not in ad
 def aB(self, a) -> dict:
  return {
  "bounty_id": int(a.c),
  "poster": str(a.ak),
  "title": str(a.ar),
  "skill": str(a.n),
  "skill_display": str(a.W),
  "min_level": str(a.g),
  "min_level_rank": ab(str(a.g)),
  "reward": str(int(a.p)),
  "status": str(a.v),
  "created_at": int(a.al),
  "claimed_at": int(a.M),
  "claimant": str(a.k),
  "claimed_username": str(a.C),
  "claimed_level": str(a.L),
  "verification_id": int(a.t),
  "content_hash": str(a.E),
  }
 def aO(self, aC, aa: int, an: int) -> list:
  if aC is None:
   return []
  aU = q(x(aa, 0), 0, 1 << 30)
  au = x(an, U)
  if au <= 0 or au > U:
   au = U
  V = []
  i = len(aC) - 1 - aU
  while i >= 0 and len(V) < au:
   a = self.ah.get(u32(int(aC[i])))
   if a is not None:
    V.append(self.aB(a))
   i -= 1
  return V
 @gl.public.view
 def require_skill(self, b: str, n: str, g: str) -> str:
  P = ab(g)
  if P < 0:
   raise gl.vm.UserError("min_level must be one of " + ", ".join(X))
  e = self.K(b, n)
  if not e["found"]:
   raise gl.vm.UserError(
   h(b) + " has no usable verification for "
   + j(n) + ": " + str(e["reason"]),
   )
  if int(e["rank"]) < P:
   raise gl.vm.UserError(
   h(b) + " is " + str(e["level"])
   + " in " + j(n) + ", " + str(g) + " required",
   )
  return json.dumps({
  "ok": True,
  "github_username": h(b),
  "skill": j(n),
  "level": str(e["level"]),
  "required": f(g),
  "verification_id": int(e.get("verification_id", 0)),
  "content_hash": str(e.get("content_hash", "")),
  })
 @gl.public.view
 def check_skill(self, b: str, n: str, g: str) -> bool:
  P = ab(g)
  if P < 0:
   return False
  e = self.K(b, n)
  if not e["found"]:
   return False
  return int(e["rank"]) >= P
 @gl.public.view
 def get_skill_report(self, b: str, n: str) -> str:
  e = self.K(b, n)
  return json.dumps({
  "github_username": h(b),
  "skill": j(n),
  "found": bool(e["found"]),
  "level": str(e["level"]),
  "rank": int(e["rank"]),
  "verification_id": int(e.get("verification_id", 0)),
  "content_hash": str(e.get("content_hash", "")),
  "identity_owner": str(e.get("identity_owner", "")),
  "verified_by": str(e.get("verified_by", "")),
  "reason": str(e.get("reason", "")),
  "oracle": str(self.J),
  })
 @gl.public.write.payable
 def post_bounty(self, ar: str, n: str, g: str) -> str:
  s = gl.message.sender_address
  value = x(gl.message.value, 0)
  if value < S:
   return self.D(s, value, "reward must be at least " + str(S))
  if value > T:
   return self.D(s, value, "reward must be at most " + str(T))
  af = " ".join(f(ar).split())[:aF]
  if af == "":
   return self.D(s, value, "title is empty")
  I = j(n)
  if I == "":
   return self.D(s, value, "skill is empty")
  P = ab(g)
  if P < 0:
   return self.D(s, value, "min_level must be one of " + ", ".join(X))
  if P == 0:
   return self.D(s, value, "min_level NONE would let anybody claim; use BEGINNER or higher")
  if len(self.F) >= Y:
   return self.D(s, value, "bounty book is full")
  if int(self.ac) >= (1 << 32) - 1:
   return self.D(s, value, "bounty id space is exhausted")
  c = int(self.ac)
  self.ac = u32(c + 1)
  a = self.ah.get_or_insert_default(u32(c))
  a.c = u32(c)
  a.ak = s
  a.ar = af
  a.n = I
  a.W = " ".join(f(n).split())[:ap]
  a.g = f(g)
  a.p = u128(value)
  a.v = ae
  a.al = u64(q(self.aM(), 0, (1 << 64) - 1))
  a.M = u64(0)
  a.k = Address(ax)
  a.C = ""
  a.L = ""
  a.t = u32(0)
  a.E = ""
  self.F.append(u32(c))
  self.az.get_or_insert_default(I).append(u32(c))
  self.aH.get_or_insert_default(s).append(u32(c))
  self.G = u128(q(int(self.G) + value, 0, (1 << 128) - 1))
  self.l = u128(q(int(self.l) + value, 0, (1 << 128) - 1))
  return json.dumps({
  "ok": True,
  "bounty_id": c,
  "reward": str(value),
  "skill": I,
  "min_level": f(g),
  })
 @gl.public.write
 def claim_bounty(self, c: int, b: str) -> str:
  a = self.at(c)
  if a is None:
   return json.dumps({"ok": False, "reason": "unknown bounty_id"})
  if not self.ai(a):
   return json.dumps({
   "ok": False,
   "reason": "bounty is " + str(a.v) + " and can never change",
   "status": str(a.v),
   })
  w = h(b)
  if w == "":
   return json.dumps({"ok": False, "reason": "github_username is empty"})
  k = o(str(gl.message.sender_address))
  e = self.K(w, str(a.n))
  R = self.Q(a, w, k, e)
  if R:
   return json.dumps(R)
  p = int(a.p)
  a.v = H
  a.k = gl.message.sender_address
  a.C = w
  a.L = str(e["level"])
  a.t = u32(q(x(e.get("verification_id"), 0), 0, (1 << 32) - 1))
  a.E = f(e.get("content_hash"))
  a.M = u64(q(self.aM(), 0, (1 << 64) - 1))
  self.N = u128(q(int(self.N) + p, 0, (1 << 128) - 1))
  self.l = u128(q(int(self.l) - p, 0, (1 << 128) - 1))
  self.aN(gl.message.sender_address, p)
  return json.dumps({
  "ok": True,
  "bounty_id": int(a.c),
  "paid": str(p),
  "to": str(a.k),
  "github_username": w,
  "identity_owner": k,
  "level": str(e["level"]),
  "verification_id": int(a.t),
  "content_hash": str(a.E),
  })
 @gl.public.write
 def withdraw_bounty(self, c: int) -> str:
  a = self.at(c)
  if a is None:
   return json.dumps({"ok": False, "reason": "unknown bounty_id"})
  if not self.ai(a):
   return json.dumps({
   "ok": False,
   "reason": "bounty is " + str(a.v) + " and can never change",
   "status": str(a.v),
   })
  if gl.message.sender_address != a.ak:
   return json.dumps({"ok": False, "reason": "only the poster may withdraw this bounty"})
  p = int(a.p)
  a.v = B
  a.M = u64(q(self.aM(), 0, (1 << 64) - 1))
  self.u = u128(q(int(self.u) + p, 0, (1 << 128) - 1))
  self.l = u128(q(int(self.l) - p, 0, (1 << 128) - 1))
  self.aN(a.ak, p)
  return json.dumps({"ok": True, "bounty_id": int(a.c), "refunded": str(p)})
 @gl.public.view
 def get_bounty(self, c: int) -> str:
  a = self.at(c)
  if a is None:
   return json.dumps({"found": False, "bounty_id": x(c, -1)})
  aX = self.aB(a)
  aX["found"] = True
  return json.dumps(aX)
 @gl.public.view
 def can_claim(self, c: int, b: str, k: str) -> str:
  a = self.at(c)
  if a is None:
   return json.dumps({"ok": False, "reason": "unknown bounty_id"})
  if not self.ai(a):
   return json.dumps({
   "ok": False,
   "reason": "bounty is " + str(a.v) + " and can never change",
   "status": str(a.v),
   })
  w = h(b)
  if w == "":
   return json.dumps({"ok": False, "reason": "github_username is empty"})
  aY = o(k)
  e = self.K(w, str(a.n))
  R = self.Q(a, w, aY, e)
  if R:
   return json.dumps(R)
  return json.dumps({
  "ok": True,
  "bounty_id": int(a.c),
  "github_username": w,
  "identity_owner": aY,
  "level": f(e.get("level")),
  "required": str(a.g),
  "reward": str(int(a.p)),
  })
 @gl.public.view
 def get_bounties(self, aa: int, an: int) -> str:
  V = self.aO(self.F, aa, an)
  return json.dumps({"total": len(self.F), "returned": len(V), "bounties": V})
 @gl.public.view
 def get_bounties_by_skill(self, n: str, aa: int, an: int) -> str:
  aC = self.az.get(j(n))
  V = self.aO(aC, aa, an)
  aV = 0 if aC is None else len(aC)
  return json.dumps({"skill": j(n), "total": aV, "returned": len(V), "bounties": V})
 @gl.public.view
 def get_terms(self) -> str:
  return json.dumps({
  "owner": str(self.z),
  "oracle": str(self.J),
  "levels": list(X),
  "statuses": [ae, H, B],
  "claims_are_identity_bound": True,
  "min_reward": str(S),
  "max_reward": str(T),
  "max_bounties": Y,
  "max_page": U,
  "total_posted": str(int(self.G)),
  "total_paid": str(int(self.N)),
  "total_withdrawn": str(int(self.u)),
  "total_refunded": str(int(self.A)),
  "open_liability": str(int(self.l)),
  "bounties": len(self.F),
  })
 @gl.public.view
 def get_oracle_config(self) -> str:
  try:
   aA = gl.contract.get_at(self.J)
   return f(aA.view().get_config())
  except Exception:
   return json.dumps({"error": "oracle unreachable", "oracle": str(self.J)})
def aj(y: int, m: int, d: int) -> int:
 y -= 1 if m <= 2 else 0
 aZ = (y if y >= 0 else y - 399) // 400
 aR = y - aZ * 400
 bf = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
 bg = aR * 365 + aR // 4 - aR // 100 + bf
 return aZ * 146097 + bg - 719468
def am(value: str) -> int:
 if not isinstance(value, str) or len(value) < 19:
  return 0
 try:
  bb = int(value[0:4])
  aE = int(value[5:7])
  aS = int(value[8:10])
  aT = int(value[11:13])
  aJ = int(value[14:16])
  aK = int(value[17:19])
 except Exception:
  return 0
 if aE < 1 or aE > 12 or aS < 1 or aS > 31:
  return 0
 if aT > 23 or aJ > 59 or aK > 60:
  return 0
 return aj(bb, aE, aS) * 86400 + aT * 3600 + aJ * 60 + aK
