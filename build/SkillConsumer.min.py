# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
from dataclasses import dataclass
import json
am = "EXPERT"
Z = "PROFICIENT"
ag = "BEGINNER"
aw = "NONE"
R = (aw, ag, Z, am)
X = "OPEN"
D = "CLAIMED"
t = "WITHDRAWN"
W = (D, t)
L = 10 ** 15
M = 100 * 10 ** 18
S = 2000
N = 50
ai = 40
an = 39
az = 120
ao = "0x0000000000000000000000000000000000000000"
def w(value, ap: int) -> int:
 try:
  if isinstance(value, bool):
   return ap
  return int(value)
 except Exception:
  return ap
def j(value) -> str:
 if value is None:
  return ""
 if isinstance(value, str):
  return value
 try:
  return str(value)
 except Exception:
  return ""
def o(value: int, aR: int, aK: int) -> int:
 if value < aR:
  return aR
 if value > aK:
  return aK
 return value
def h(value) -> str:
 return j(value).strip().lower()[:an]
def f(value) -> str:
 return " ".join(j(value).split()).lower()[:ai]
def U(aj) -> int:
 aU = j(aj)
 for i in range(len(R)):
  if R[i] == aU:
   return i
 return -1
def aF(value) -> dict:
 if isinstance(value, dict):
  return value
 try:
  aA = json.loads(j(value))
 except Exception:
  return {}
 if isinstance(aA, dict):
  return aA
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
 c: u32
 ac: Address
 ak: str
 l: str
 Q: str
 e: str
 n: u128
 z: str
 ad: u64
 H: u64
 O: Address
 u: str
 G: str
 q: u32
 A: str
class SkillConsumer(gl.Contract):
 aI: Address
 F: Address
 aa: TreeMap[u32, Bounty]
 B: DynArray[u32]
 V: u32
 aq: TreeMap[str, DynArray[u32]]
 aB: TreeMap[Address, DynArray[u32]]
 C: u128
 I: u128
 r: u128
 s: u128
 k: u128
 def __init__(self, F: str):
  self.aI = gl.message.sender_address
  self.F = Address(j(F))
  self.V = u32(1)
  self.C = u128(0)
  self.I = u128(0)
  self.r = u128(0)
  self.s = u128(0)
  self.k = u128(0)
 def aG(self) -> int:
  return ae(gl.message_raw.get("datetime", ""))
 def aH(self, to: Address, aC: int) -> None:
  if aC <= 0:
   return
  _Payee(Address(str(to))).emit_transfer(value=u256(int(aC)))
 def x(self, p: Address, value: int, aL: str) -> str:
  if value > 0:
   self.aH(p, value)
   self.s = u128(o(int(self.s) + value, 0, (1 << 128) - 1))
  return json.dumps({"ok": False, "reason": aL, "refunded": str(value)})
 def J(self, b: str, l: str) -> dict:
  try:
   ar = gl.get_contract_at(self.F)
   aY = ar.view().get_latest(
   h(b), f(l),
   )
  except Exception:
   return {"found": False, "level": "", "rank": -1, "reason": "oracle unreachable"}
  v = aF(aY)
  if not bool(v.get("found", False)):
   return {"found": False, "level": "", "rank": -1, "reason": "no resolved verification"}
  if not bool(v.get("fresh", True)):
   return {"found": False, "level": j(v.get("level")), "rank": -1, "reason": "verification is stale"}
  aj = j(v.get("level"))
  return {
  "found": True,
  "level": aj,
  "rank": U(aj),
  "verification_id": w(v.get("verification_id"), 0),
  "content_hash": j(v.get("content_hash")),
  "repo_count": w(v.get("repo_count"), 0),
  "reason": "",
  }
 def ax(self, c: int):
  return self.aa.get(u32(o(w(c, -1), 0, (1 << 32) - 1)))
 def at(self, a) -> bool:
  if a is None:
   return False
  return str(a.z) not in W
 def au(self, a) -> dict:
  return {
  "bounty_id": int(a.c),
  "poster": str(a.ac),
  "title": str(a.ak),
  "skill": str(a.l),
  "skill_display": str(a.Q),
  "min_level": str(a.e),
  "min_level_rank": U(str(a.e)),
  "reward": str(int(a.n)),
  "status": str(a.z),
  "created_at": int(a.ad),
  "claimed_at": int(a.H),
  "claimant": str(a.O),
  "claimed_username": str(a.u),
  "claimed_level": str(a.G),
  "verification_id": int(a.q),
  "content_hash": str(a.A),
  }
 def aJ(self, av, T: int, af: int) -> list:
  if av is None:
   return []
  aP = o(w(T, 0), 0, 1 << 30)
  al = w(af, N)
  if al <= 0 or al > N:
   al = N
  P = []
  i = len(av) - 1 - aP
  while i >= 0 and len(P) < al:
   a = self.aa.get(u32(int(av[i])))
   if a is not None:
    P.append(self.au(a))
   i -= 1
  return P
 @gl.public.view
 def require_skill(self, b: str, l: str, e: str) -> str:
  K = U(e)
  if K < 0:
   raise gl.vm.UserError("min_level must be one of " + ", ".join(R))
  g = self.J(b, l)
  if not g["found"]:
   raise gl.vm.UserError(
   h(b) + " has no usable verification for "
   + f(l) + ": " + str(g["reason"]),
   )
  if int(g["rank"]) < K:
   raise gl.vm.UserError(
   h(b) + " is " + str(g["level"])
   + " in " + f(l) + ", " + str(e) + " required",
   )
  return json.dumps({
  "ok": True,
  "github_username": h(b),
  "skill": f(l),
  "level": str(g["level"]),
  "required": j(e),
  "verification_id": int(g.get("verification_id", 0)),
  "content_hash": str(g.get("content_hash", "")),
  })
 @gl.public.view
 def check_skill(self, b: str, l: str, e: str) -> bool:
  K = U(e)
  if K < 0:
   return False
  g = self.J(b, l)
  if not g["found"]:
   return False
  return int(g["rank"]) >= K
 @gl.public.view
 def get_skill_report(self, b: str, l: str) -> str:
  g = self.J(b, l)
  return json.dumps({
  "github_username": h(b),
  "skill": f(l),
  "found": bool(g["found"]),
  "level": str(g["level"]),
  "rank": int(g["rank"]),
  "verification_id": int(g.get("verification_id", 0)),
  "content_hash": str(g.get("content_hash", "")),
  "reason": str(g.get("reason", "")),
  "oracle": str(self.F),
  })
 @gl.public.write.payable
 def post_bounty(self, ak: str, l: str, e: str) -> str:
  p = gl.message.sender_address
  value = w(gl.message.value, 0)
  if value < L:
   return self.x(p, value, "reward must be at least " + str(L))
  if value > M:
   return self.x(p, value, "reward must be at most " + str(M))
  Y = " ".join(j(ak).split())[:az]
  if Y == "":
   return self.x(p, value, "title is empty")
  E = f(l)
  if E == "":
   return self.x(p, value, "skill is empty")
  K = U(e)
  if K < 0:
   return self.x(p, value, "min_level must be one of " + ", ".join(R))
  if K == 0:
   return self.x(p, value, "min_level NONE would let anybody claim; use BEGINNER or higher")
  if len(self.B) >= S:
   return self.x(p, value, "bounty book is full")
  if int(self.V) >= (1 << 32) - 1:
   return self.x(p, value, "bounty id space is exhausted")
  c = int(self.V)
  self.V = u32(c + 1)
  a = self.aa.get_or_insert_default(u32(c))
  a.c = u32(c)
  a.ac = p
  a.ak = Y
  a.l = E
  a.Q = " ".join(j(l).split())[:ai]
  a.e = j(e)
  a.n = u128(value)
  a.z = X
  a.ad = u64(o(self.aG(), 0, (1 << 64) - 1))
  a.H = u64(0)
  a.O = Address(ao)
  a.u = ""
  a.G = ""
  a.q = u32(0)
  a.A = ""
  self.B.append(u32(c))
  self.aq.get_or_insert_default(E).append(u32(c))
  self.aB.get_or_insert_default(p).append(u32(c))
  self.C = u128(o(int(self.C) + value, 0, (1 << 128) - 1))
  self.k = u128(o(int(self.k) + value, 0, (1 << 128) - 1))
  return json.dumps({
  "ok": True,
  "bounty_id": c,
  "reward": str(value),
  "skill": E,
  "min_level": j(e),
  })
 @gl.public.write
 def claim_bounty(self, c: int, b: str) -> str:
  a = self.ax(c)
  if a is None:
   return json.dumps({"ok": False, "reason": "unknown bounty_id"})
  if not self.at(a):
   return json.dumps({
   "ok": False,
   "reason": "bounty is " + str(a.z) + " and can never change",
   "status": str(a.z),
   })
  ah = h(b)
  if ah == "":
   return json.dumps({"ok": False, "reason": "github_username is empty"})
  g = self.J(ah, str(a.l))
  if not g["found"]:
   return json.dumps({
   "ok": False,
   "reason": ah + " has no usable verification for " + str(a.l)
   + ": " + str(g["reason"]),
   "required": str(a.e),
   })
  K = U(str(a.e))
  aV = int(g["rank"])
  if aV < K:
   return json.dumps({
   "ok": False,
   "reason": ah + " is " + str(g["level"]) + ", " + str(a.e) + " required",
   "level": str(g["level"]),
   "required": str(a.e),
   })
  n = int(a.n)
  a.z = D
  a.O = gl.message.sender_address
  a.u = ah
  a.G = str(g["level"])
  a.q = u32(o(w(g.get("verification_id"), 0), 0, (1 << 32) - 1))
  a.A = j(g.get("content_hash"))
  a.H = u64(o(self.aG(), 0, (1 << 64) - 1))
  self.I = u128(o(int(self.I) + n, 0, (1 << 128) - 1))
  self.k = u128(o(int(self.k) - n, 0, (1 << 128) - 1))
  self.aH(gl.message.sender_address, n)
  return json.dumps({
  "ok": True,
  "bounty_id": int(a.c),
  "paid": str(n),
  "to": str(a.O),
  "github_username": ah,
  "level": str(g["level"]),
  "verification_id": int(a.q),
  "content_hash": str(a.A),
  })
 @gl.public.write
 def withdraw_bounty(self, c: int) -> str:
  a = self.ax(c)
  if a is None:
   return json.dumps({"ok": False, "reason": "unknown bounty_id"})
  if not self.at(a):
   return json.dumps({
   "ok": False,
   "reason": "bounty is " + str(a.z) + " and can never change",
   "status": str(a.z),
   })
  if gl.message.sender_address != a.ac:
   return json.dumps({"ok": False, "reason": "only the poster may withdraw this bounty"})
  n = int(a.n)
  a.z = t
  a.H = u64(o(self.aG(), 0, (1 << 64) - 1))
  self.r = u128(o(int(self.r) + n, 0, (1 << 128) - 1))
  self.k = u128(o(int(self.k) - n, 0, (1 << 128) - 1))
  self.aH(a.ac, n)
  return json.dumps({"ok": True, "bounty_id": int(a.c), "refunded": str(n)})
 @gl.public.view
 def get_bounty(self, c: int) -> str:
  a = self.ax(c)
  if a is None:
   return json.dumps({"found": False, "bounty_id": w(c, -1)})
  aS = self.au(a)
  aS["found"] = True
  return json.dumps(aS)
 @gl.public.view
 def get_bounties(self, T: int, af: int) -> str:
  P = self.aJ(self.B, T, af)
  return json.dumps({"total": len(self.B), "returned": len(P), "bounties": P})
 @gl.public.view
 def get_bounties_by_skill(self, l: str, T: int, af: int) -> str:
  av = self.aq.get(f(l))
  P = self.aJ(av, T, af)
  aQ = 0 if av is None else len(av)
  return json.dumps({"skill": f(l), "total": aQ, "returned": len(P), "bounties": P})
 @gl.public.view
 def get_terms(self) -> str:
  return json.dumps({
  "owner": str(self.aI),
  "oracle": str(self.F),
  "levels": list(R),
  "statuses": [X, D, t],
  "min_reward": str(L),
  "max_reward": str(M),
  "max_bounties": S,
  "max_page": N,
  "total_posted": str(int(self.C)),
  "total_paid": str(int(self.I)),
  "total_withdrawn": str(int(self.r)),
  "total_refunded": str(int(self.s)),
  "open_liability": str(int(self.k)),
  "bounties": len(self.B),
  })
 @gl.public.view
 def get_oracle_config(self) -> str:
  try:
   ar = gl.get_contract_at(self.F)
   return j(ar.view().get_config())
  except Exception:
   return json.dumps({"error": "oracle unreachable", "oracle": str(self.F)})
def ab(y: int, m: int, d: int) -> int:
 y -= 1 if m <= 2 else 0
 aT = (y if y >= 0 else y - 399) // 400
 aM = y - aT * 400
 ba = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
 bb = aM * 365 + aM // 4 - aM // 100 + ba
 return aT * 146097 + bb - 719468
def ae(value: str) -> int:
 if not isinstance(value, str) or len(value) < 19:
  return 0
 try:
  aW = int(value[0:4])
  ay = int(value[5:7])
  aN = int(value[8:10])
  aO = int(value[11:13])
  aD = int(value[14:16])
  aE = int(value[17:19])
 except Exception:
  return 0
 if ay < 1 or ay > 12 or aN < 1 or aN > 31:
  return 0
 if aO > 23 or aD > 59 or aE > 60:
  return 0
 return ab(aW, ay, aN) * 86400 + aO * 3600 + aD * 60 + aE
