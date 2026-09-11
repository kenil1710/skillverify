# v0.3.0
# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng" }
import genlayer as gl
from genlayer import *
from dataclasses import dataclass
import json
aB = "EXPERT"
ad = "PROFICIENT"
am = "BEGINNER"
ah = "NONE"
bK = (ah, am, ad, aB)
bg = 5
bh = 1000
aC = 3
aD = 500
aQ = 1
Y = "NO_SUCH_USER"
k = "UNAVAILABLE"
by = (aB, ad, am, ah, Y, k)
aR = "PENDING"
ai = "RESOLVED"
U = "STALLED"
bv = (ai, U)
S = 39
ar = 40
av = 3
aw = 100
bz = 100
bw = 100
bA = 0
bs = 10**18
bE = 300
bi = 86400
aO = 3600
at = 60
au = 30 * 86400
bx = 0
bc = 365 * 86400
aY = 50
aj = 1000
bB = "github_repo_size_kb"
bd = "https://api.github.com/search/repositories"
ck = "0x0000000000000000000000000000000000000000"
cC = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
dj = "0123456789ABCDEF"
def g(value, cl: int) -> int:
 try:
  if isinstance(value, bool):
   return cl
  return int(value)
 except Exception:
  return cl
def v(value) -> str:
 if value is None:
  return ""
 if isinstance(value, str):
  return value
 try:
  return str(value)
 except Exception:
  return ""
def r(value: int, dk: int, cU: int) -> int:
 if value < dk:
  return dk
 if value > cU:
  return cU
 return value
def bF(y: int, m: int, d: int) -> int:
 y -= 1 if m <= 2 else 0
 dl = (y if y >= 0 else y - 399) // 400
 cV = y - dl * 400
 dv = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
 dw = cV * 365 + cV // 4 - cV // 100 + dv
 return dl * 146097 + dw - 719468
def bL(value: str) -> int:
 if not isinstance(value, str) or len(value) < 19:
  return 0
 try:
  do = int(value[0:4])
  cD = int(value[5:7])
  cW = int(value[8:10])
  cX = int(value[11:13])
  cJ = int(value[14:16])
  cK = int(value[17:19])
 except Exception:
  return 0
 if cD < 1 or cD > 12 or cW < 1 or cW > 31:
  return 0
 if cX > 23 or cJ > 59 or cK > 60:
  return 0
 return bF(do, cD, cW) * 86400 + cX * 3600 + cJ * 60 + cK
def dp(text: str) -> str:
 if not isinstance(text, str):
  return ""
 if text == "":
  return ""
 h = 0xCBF29CE484222325
 for cm in text.encode("utf-8"):
  h = ((h ^ cm) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
 return "%016x" % h
def cf(x: str, j: str, A: str, t: int, o: int) -> str:
 df = [
 f(x),
 l(j),
 v(A),
 str(g(t, 0)),
 str(g(o, 0)),
 ]
 return dp("\x1f".join(df))
def f(value) -> str:
 text = v(value).strip()
 return text.lower()[:S]
def l(value) -> str:
 return " ".join(v(value).split()).lower()[:ar]
def bZ(value) -> str:
 return " ".join(v(value).split())[:ar]
def D(value) -> str:
 return v(value).strip().lower()
def aE(value) -> bool:
 text = D(value)
 if text == "" or text == "none":
  return True
 if text.startswith("0x"):
  text = text[2:]
 return text.strip("0") == ""
def ay(value) -> str:
 text = v(value).strip()
 if text == "":
  return "github_username is empty"
 if len(text) > S:
  return "github_username exceeds " + str(S) + " characters"
 bt = text.lower()
 for ch in bt:
  if not (("a" <= ch <= "z") or ("0" <= ch <= "9") or ch == "-"):
   return "github_username may only contain letters, digits and hyphens"
 if bt.startswith("-") or bt.endswith("-"):
  return "github_username may not start or end with a hyphen"
 if bt.find("--") >= 0:
  return "github_username may not contain consecutive hyphens"
 return ""
def ca(value) -> str:
 text = v(value)
 bj = " ".join(text.split())
 if bj == "":
  return "skill is empty"
 if len(bj) > ar:
  return "skill exceeds " + str(ar) + " characters"
 for ch in bj.lower():
  ok = ("a" <= ch <= "z") or ("0" <= ch <= "9") or ch in " +#-._"
  if not ok:
   return "skill may only contain letters, digits, spaces and + # - . _"
 return ""
def cY(value: str) -> str:
 if not isinstance(value, str):
  return ""
 cZ = []
 for cm in value.encode("utf-8"):
  ch = chr(cm)
  if ch in cC:
   cZ.append(ch)
  else:
   cZ.append("%" + dj[(cm >> 4) & 0xF] + dj[cm & 0xF])
 return "".join(cZ)
def cw(x: str, j: str) -> str:
 Z = cY(f(x))
 bk = cY(l(j))
 q = "user:" + Z + "%20language:%22" + bk + "%22"
 return bd + "?per_page=" + str(bz) + "&sort=updated&q=" + q
def bu(A) -> int:
 text = v(A)
 for i in range(len(bK)):
  if bK[i] == text:
   return i
 return -1
def bM(t: int, o: int) -> str:
 bN = g(t, 0)
 cE = g(o, 0)
 if bN >= bg and cE >= bh:
  return aB
 if bN >= aC and cE >= aD:
  return ad
 if bN >= aQ:
  return am
 return ah
def da(an, j: str) -> dict:
 bk = l(j)
 if not isinstance(an, dict):
  return {"ok": False, "repo_count": 0, "total_bytes": 0, "index_count": 0, "top_repos": [], "level": ah}
 cF = an.get("items")
 if not isinstance(cF, list):
  cF = []
 aS = []
 bO = 0
 for ci in cF[:bw]:
  if not isinstance(ci, dict):
   continue
  if l(ci.get("language")) != bk:
   continue
  ao = ci.get("size", 0)
  if isinstance(ao, bool) or not isinstance(ao, int):
   ao = 0
  ao = r(int(ao), 0, 1 << 40)
  cn = v(ci.get("name"))[:aw]
  aS.append({"name": cn, "bytes": ao * 1024})
  bO += ao * 1024
 aS.sort(key=lambda aF: (-aF["bytes"], aF["name"]))
 return {
 "ok": True,
 "repo_count": len(aS),
 "total_bytes": bO,
 "index_count": r(g(an.get("total_count", 0), 0), 0, 1 << 40),
 "incomplete": bool(an.get("incomplete_results", False)),
 "top_repos": [aF["name"] for aF in aS[:av]],
 "level": bM(len(aS), bO),
 }
def cd(bl) -> int:
 if bl is None:
  return 0
 try:
  return len(bl)
 except Exception:
  return 0
def ce(dx) -> list:
 text = v(dx)
 if text == "":
  return []
 try:
  bm = json.loads(text)
 except Exception:
  return []
 if not isinstance(bm, list):
  return []
 return [v(cn)[:aw] for cn in bm[:av]]
def cG(bP) -> int:
 s = getattr(bP, "status_code", None)
 if s is None:
  s = getattr(bP, "status", None)
 if s is None:
  return 0
 return g(s, 0)
def cP(bP) -> str:
 b = getattr(bP, "body", None)
 if b is None:
  b = getattr(bP, "text", None)
 if b is None:
  return ""
 if isinstance(b, bytes):
  return b.decode("utf-8", errors="ignore")
 return v(b)
def cL(x: str, j: str) -> dict:
 dm = cw(x, j)
 try:
  try:
   bP = gl.nondet.web.request(dm, method="GET")
  except AttributeError:
   bP = gl.nondet.web.get(dm)
  status = cG(bP)
  body = cP(bP)
 except Exception as dy:
  return {"axis": k, "status": 0, "reason": "fetch failed: " + v(dy)[:160]}
 if status == 422:
  return {"axis": Y, "status": status, "reason": "GitHub cannot search this user"}
 if status != 200:
  return {"axis": k, "status": status, "reason": "GitHub answered " + str(status)}
 try:
  an = json.loads(body)
 except Exception:
  return {"axis": k, "status": status, "reason": "response was not JSON"}
 aG = da(an, j)
 if not aG["ok"]:
  return {"axis": k, "status": status, "reason": "response had no items array"}
 return {
 "axis": aG["level"],
 "status": status,
 "repo_count": aG["repo_count"],
 "total_bytes": aG["total_bytes"],
 "index_count": aG["index_count"],
 "incomplete": aG["incomplete"],
 "top_repos": aG["top_repos"],
 "reason": "",
 }
def co(aH) -> str:
 if not isinstance(aH, dict):
  return k
 ax = v(aH.get("axis"))
 if ax in by:
  return ax
 return k
def bn(aH) -> str:
 ax = co(aH)
 if bu(ax) < 0:
  return ax
 if not isinstance(aH, dict):
  return k
 bN = g(aH.get("repo_count"), -1)
 cE = g(aH.get("total_bytes"), -1)
 return ax + "\x1f" + str(bN) + "\x1f" + str(cE)
def aK(x: str, j: str) -> dict:
 Z = str(x)
 bk = str(j)
 def leader_fn() -> dict:
  return cL(Z, bk)
 def validator_fn(be: gl.vm.Result) -> bool:
  if not isinstance(be, gl.vm.Return):
   leader_fn()
   return False
  dq = bn(leader_fn())
  db = bn(be.calldata)
  return dq == db
 B = gl.vm.run_nondet(leader_fn, validator_fn)
 if not isinstance(B, dict):
  return {"axis": k, "status": 0, "reason": "nondet returned no document"}
 return B
@gl.storage.allow
@dataclass
class Verification:
 e: u32
 c: str
 aI: str
 j: str
 bf: str
 status: str
 A: str
 t: u32
 o: u128
 Q: u32
 aL: str
 L: str
 p: u64
 bC: Address
 ak: u64
 u: u64
 cp: u128
 bo: u128
 bD: str
 K: u32
 az: bool
 ae: bool
 w: str
 aa: u32
@gl.evm.contract_interface
class _Payee:
 class View:
  pass
 class Write:
  pass
class SkillVerify(gl.contract.Contract):
 O: Address
 aT: bool
 ab: gl.storage.TreeMap[u32, Verification]
 bG: gl.storage.DynArray[u32]
 aU: u32
 cS: gl.storage.TreeMap[str, gl.storage.DynArray[u32]]
 cy: gl.storage.TreeMap[str, gl.storage.DynArray[u32]]
 cq: gl.storage.TreeMap[str, gl.storage.DynArray[u32]]
 al: gl.storage.TreeMap[str, u32]
 bH: gl.storage.TreeMap[str, u32]
 bQ: gl.storage.TreeMap[str, Address]
 aq: gl.storage.TreeMap[str, u64]
 aM: gl.storage.TreeMap[Address, u64]
 aV: u128
 T: u64
 u: u64
 C: u64
 H: u32
 V: u32
 R: u32
 W: u32
 G: u32
 ac: u32
 z: u32
 P: u32
 M: u128
 N: u128
 X: u128
 def __init__(self, aV: int = bA):
  self.O = gl.message.sender_address
  self.aT = False
  self.aU = u32(1)
  self.aV = u128(r(g(aV, bA), 0, bs))
  self.T = u64(bE)
  self.u = u64(aO)
  self.C = u64(bx)
  self.H = u32(0)
  self.V = u32(0)
  self.R = u32(0)
  self.W = u32(0)
  self.G = u32(0)
  self.ac = u32(0)
  self.z = u32(0)
  self.P = u32(0)
  self.M = u128(0)
  self.N = u128(0)
  self.X = u128(0)
 def cb(self) -> int:
  return bL(gl.message.raw.get("datetime", ""))
 def cQ(self, to: Address, bR: int) -> None:
  if bR <= 0:
   return
  _Payee(Address(str(to))).emit_transfer(value=u256(int(bR)))
 def ap(self, E: Address, value: int, bp: str) -> str:
  if value > 0:
   self.cQ(E, value)
   self.X = u128(r(int(self.X) + value, 0, (1 << 128) - 1))
  return json.dumps({"ok": False, "reason": bp, "refunded": str(value)})
 def J(self, x: str) -> str:
  O = self.bQ.get(x)
  if O is None:
   return ""
  text = D(str(O))
  if aE(text):
   return ""
  return text
 def cg(self, x: str) -> dict:
  O = self.J(x)
  return {
  "github_username": x,
  "registered": O != "",
  "identity_owner": O,
  "identity_registered_at": g(self.aq.get(x), 0) if O else 0,
  }
 def aN(self, x: str, j: str) -> str:
  return f(x) + "\x1f" + l(j)
 def cH(self, e: int):
  return self.ab.get(u32(r(g(e, -1), 0, (1 << 32) - 1)))
 def cr(self, a) -> bool:
  if a is None:
   return False
  return str(a.status) not in bv
 def cs(self, key: str, dg, e: int) -> bool:
  bl = dg.get_or_insert_default(key)
  dh = len(bl) == 0
  bl.append(u32(e))
  return dh
 def aA(self, cx: int) -> int:
  return r(cx + 1, 0, (1 << 32) - 1)
 def aZ(self, a) -> dict:
  aW = self.cb()
  p = int(a.p)
  dn = (aW - p) if (p > 0 and aW > p) else 0
  return {
  "verification_id": int(a.e),
  "github_username": str(a.c),
  "username_display": str(a.aI),
  "skill": str(a.j),
  "skill_display": str(a.bf),
  "status": str(a.status),
  "level": str(a.A),
  "level_rank": bu(str(a.A)),
  "repo_count": int(a.t),
  "total_bytes": str(int(a.o)),
  "bytes_basis": str(a.bD),
  "index_count": int(a.Q),
  "top_repos": ce(str(a.aL)),
  "content_hash": str(a.L),
  "verified_at": p,
  "verified_by": str(a.bC),
  "identity_owner": self.J(str(a.c)),
  "requested_at": int(a.ak),
  "age_seconds": dn,
  "stale": bool(int(self.C) > 0 and p > 0 and dn > int(self.C)),
  "resolve_window": int(a.u),
  "settle_stalled_at": int(a.ak) + int(a.u),
  "fee_paid": str(int(a.cp)),
  "fee_snapshot": str(int(a.bo)),
  "attempts": int(a.K),
  "user_found": bool(a.az),
  "incomplete_index": bool(a.ae),
  "last_reason": str(a.w),
  "http_status": int(a.aa),
  }
 def cM(self, a, B: dict) -> dict:
  ax = co(B)
  status_code = r(g(B.get("status"), 0), 0, (1 << 32) - 1)
  bp = v(B.get("reason"))[:200]
  if ax == k:
   a.K = u32(r(int(a.K) + 1, 0, aj))
   a.w = bp if bp else "source unavailable"
   a.aa = u32(status_code)
   return {"resolved": False, "axis": ax, "reason": a.w}
  if ax == Y:
   A = ah
   t = 0
   o = 0
   Q = 0
   dc = []
   bS = False
   bT = False
  else:
   A = ax
   t = r(g(B.get("repo_count"), 0), 0, (1 << 32) - 1)
   o = r(g(B.get("total_bytes"), 0), 0, (1 << 128) - 1)
   Q = r(g(B.get("index_count"), 0), 0, (1 << 32) - 1)
   cz = B.get("top_repos")
   dc = []
   if isinstance(cz, list):
    for cn in cz[:av]:
     dc.append(v(cn)[:aw])
   bS = True
   bT = bool(B.get("incomplete", False))
   bU = bM(t, o)
   if bU != A:
    a.K = u32(r(int(a.K) + 1, 0, aj))
    a.w = (
    "incoherent result: level " + A + " with " + str(t)
    + " repos and " + str(o) + " bytes, which is " + bU
    )[:200]
    a.aa = u32(status_code)
    return {"resolved": False, "axis": k,
    "incoherent": True, "reason": a.w}
  a.A = A
  a.t = u32(t)
  a.o = u128(o)
  a.Q = u32(Q)
  a.aL = json.dumps(dc)
  a.az = bS
  a.ae = bT
  a.aa = u32(status_code)
  a.w = bp
  a.K = u32(r(int(a.K) + 1, 0, aj))
  a.p = u64(r(self.cb(), 0, (1 << 64) - 1))
  a.L = cf(
  str(a.c), str(a.j), A, t, o,
  )
  a.status = ai
  return {"resolved": True, "axis": ax, "level": A}
 def bI(self, key: str) -> None:
  self.bH[key] = u32(0)
 def aP(self, key: str) -> int:
  return g(self.bH.get(key), 0) - 1
 def cR(self, bV, aJ: int, bW: int) -> list:
  di = r(g(aJ, 0), 0, 1 << 30)
  cj = g(bW, aY)
  if cj <= 0 or cj > aY:
   cj = aY
  if bV is None:
   return []
  ba = []
  bO = len(bV)
  i = bO - 1 - di
  while i >= 0 and len(ba) < cj:
   a = self.ab.get(u32(int(bV[i])))
   if a is not None:
    ba.append(self.aZ(a))
   i -= 1
  return ba
 @gl.public.write
 def register_identity(self, c: str) -> str:
  E = gl.message.sender_address
  if self.aT:
   return json.dumps({"ok": False, "reason": "contract is paused"})
  af = ay(c)
  if af:
   return json.dumps({"ok": False, "reason": af})
  Z = f(c)
  ct = self.J(Z)
  if ct != "":
   if ct == D(str(E)):
    return json.dumps({
    "ok": True, "github_username": Z, "identity_owner": ct,
    "already_registered": True,
    "registered_at": g(self.aq.get(Z), 0),
    })
   return json.dumps({
   "ok": False, "github_username": Z, "identity_owner": ct,
   "reason": Z + " is already registered to " + ct
   + " and a registration can never be moved",
   })
  self.bQ[Z] = E
  self.aq[Z] = u64(r(self.cb(), 0, (1 << 64) - 1))
  self.P = u32(self.aA(int(self.P)))
  return json.dumps({
  "ok": True,
  "github_username": Z,
  "identity_owner": D(str(E)),
  "already_registered": False,
  "registered_at": g(self.aq.get(Z), 0),
  })
 @gl.public.write.payable
 def verify_skill(self, c: str, j: str) -> str:
  E = gl.message.sender_address
  value = g(gl.message.value, 0)
  if self.aT:
   return self.ap(E, value, "contract is paused")
  af = ay(c)
  if af:
   return self.ap(E, value, af)
  af = ca(j)
  if af:
   return self.ap(E, value, af)
  aV = int(self.aV)
  if value < aV:
   return self.ap(E, value, "fee is " + str(aV) + " and " + str(value) + " was sent")
  aW = self.cb()
  T = int(self.T)
  dd = g(self.aM.get(E), 0)
  if T > 0 and dd > 0 and aW > 0:
   cA = aW - dd
   if 0 <= cA < T:
    return self.ap(E, value, "rate limited, " + str(T - cA) + "s remaining")
  key = self.aN(c, j)
  cB = self.aP(key)
  if cB >= 0:
   return self.ap(
   E, value,
   "verification " + str(cB) + " for this username and skill is already in flight",
   )
  if int(self.aU) >= (1 << 32) - 1:
   return self.ap(E, value, "verification id space is exhausted")
  B = aK(f(c), l(j))
  e = int(self.aU)
  self.aU = u32(e + 1)
  a = self.ab.get_or_insert_default(u32(e))
  a.e = u32(e)
  a.c = f(c)
  a.aI = v(c).strip()[:S]
  a.j = l(j)
  a.bf = bZ(j)
  a.status = aR
  a.A = ""
  a.t = u32(0)
  a.o = u128(0)
  a.Q = u32(0)
  a.L = ""
  a.aL = "[]"
  a.p = u64(0)
  a.bC = E
  a.ak = u64(r(aW, 0, (1 << 64) - 1))
  a.u = u64(int(self.u))
  a.cp = u128(r(aV, 0, (1 << 128) - 1))
  a.bo = u128(r(aV, 0, (1 << 128) - 1))
  a.bD = bB
  a.K = u32(0)
  a.az = False
  a.ae = False
  a.w = ""
  a.aa = u32(0)
  self.bG.append(u32(e))
  if self.cs(a.c, self.cy, e):
   self.V = u32(self.aA(int(self.V)))
  if self.cs(a.j, self.cq, e):
   self.R = u32(self.aA(int(self.R)))
  if self.cs(key, self.cS, e):
   self.W = u32(self.aA(int(self.W)))
  self.H = u32(self.aA(int(self.H)))
  self.aM[E] = u64(r(aW, 0, (1 << 64) - 1))
  self.M = u128(r(int(self.M) + aV, 0, (1 << 128) - 1))
  cc = self.cM(a, B)
  if cc["resolved"]:
   self.al[key] = u32(e)
   self.G = u32(self.aA(int(self.G)))
   self.bI(key)
  else:
   self.bH[key] = u32(e + 1)
   self.z = u32(self.aA(int(self.z)))
  bX = value - aV
  if bX > 0:
   self.cQ(E, bX)
  return json.dumps({
  "ok": True,
  "verification_id": e,
  "status": str(a.status),
  "level": str(a.A),
  "repo_count": int(a.t),
  "total_bytes": str(int(a.o)),
  "top_repos": ce(str(a.aL)),
  "content_hash": str(a.L),
  "user_found": bool(a.az),
  "reason": str(a.w),
  "change_returned": str(bX if bX > 0 else 0),
  })
 @gl.public.write
 def resolve_pending(self, e: int) -> str:
  a = self.cH(e)
  if a is None:
   return json.dumps({"ok": False, "reason": "unknown verification_id"})
  if not self.cr(a):
   return json.dumps({
   "ok": False,
   "reason": "verification is " + str(a.status) + " and can never change",
   "status": str(a.status),
   "level": str(a.A),
   })
  if int(a.K) >= aj:
   return json.dumps({"ok": False, "reason": "attempt ceiling reached, settle it stalled"})
  key = self.aN(str(a.c), str(a.j))
  B = aK(str(a.c), str(a.j))
  cc = self.cM(a, B)
  if cc["resolved"]:
   self.al[key] = u32(int(a.e))
   self.G = u32(self.aA(int(self.G)))
   self.z = u32(r(int(self.z) - 1, 0, (1 << 32) - 1))
   self.bI(key)
  return json.dumps({
  "ok": True,
  "verification_id": int(a.e),
  "status": str(a.status),
  "level": str(a.A),
  "repo_count": int(a.t),
  "total_bytes": str(int(a.o)),
  "content_hash": str(a.L),
  "attempts": int(a.K),
  "reason": str(a.w),
  })
 @gl.public.write
 def settle_stalled(self, e: int) -> str:
  a = self.cH(e)
  if a is None:
   return json.dumps({"ok": False, "reason": "unknown verification_id"})
  if not self.cr(a):
   return json.dumps({
   "ok": False,
   "reason": "verification is already " + str(a.status),
   "status": str(a.status),
   })
  aW = self.cb()
  de = int(a.ak) + int(a.u)
  if aW < de:
   return json.dumps({
   "ok": False,
   "reason": "resolution window has " + str(de - aW) + "s left",
   "settle_stalled_at": de,
   })
  key = self.aN(str(a.c), str(a.j))
  a.status = U
  a.A = ""
  a.w = "unresolved after " + str(int(a.u)) + "s"
  a.L = ""
  self.ac = u32(self.aA(int(self.ac)))
  self.z = u32(r(int(self.z) - 1, 0, (1 << 32) - 1))
  self.bI(key)
  return json.dumps({
  "ok": True,
  "verification_id": int(a.e),
  "status": U,
  "reason": str(a.w),
  })
 @gl.public.view
 def get_verification(self, e: int) -> str:
  a = self.cH(e)
  if a is None:
   return json.dumps({"found": False, "verification_id": g(e, -1)})
  aF = self.aZ(a)
  aF["found"] = True
  return json.dumps(aF)
 @gl.public.view
 def get_verifications_by_user(self, c: str, aJ: int, bW: int) -> str:
  Z = f(c)
  bV = self.cy.get(Z)
  ba = self.cR(bV, aJ, bW)
  return json.dumps({
  "github_username": Z,
  "total": cd(bV),
  "returned": len(ba),
  "offset": r(g(aJ, 0), 0, 1 << 30),
  "verifications": ba,
  })
 @gl.public.view
 def get_verifications_by_skill(self, j: str, aJ: int, bW: int) -> str:
  bk = l(j)
  bV = self.cq.get(bk)
  ba = self.cR(bV, aJ, bW)
  return json.dumps({
  "skill": bk,
  "total": cd(bV),
  "returned": len(ba),
  "offset": r(g(aJ, 0), 0, 1 << 30),
  "verifications": ba,
  })
 @gl.public.view
 def is_verified(self, c: str, j: str, ag: str) -> bool:
  cu = bu(ag)
  if cu < 0:
   return False
  a = self.I(c, j)
  if a is None:
   return False
  if not self.bq(a):
   return False
  return bu(str(a.A)) >= cu
 @gl.public.view
 def require_verified(self, c: str, j: str, ag: str) -> str:
  cu = bu(ag)
  if cu < 0:
   raise gl.vm.UserError("min_level must be one of " + ", ".join(bK))
  a = self.I(c, j)
  if a is None:
   raise gl.vm.UserError(
   "no resolved verification for " + f(c)
   + " / " + l(j),
   )
  if not self.bq(a):
   raise gl.vm.UserError("verification " + str(int(a.e)) + " is stale")
  dr = bu(str(a.A))
  if dr < cu:
   raise gl.vm.UserError(
   f(c) + " is " + str(a.A)
   + " in " + l(j) + ", " + str(ag) + " required",
   )
  aF = self.aZ(a)
  aF["ok"] = True
  return json.dumps(aF)
 @gl.public.view
 def get_identity(self, c: str) -> str:
  return json.dumps(self.cg(f(c)))
 @gl.public.view
 def owns_identity(self, c: str, bJ: str) -> bool:
  O = self.J(f(c))
  if O == "":
   return False
  n = D(bJ)
  if aE(n):
   return False
  return O == n
 @gl.public.view
 def is_verified_identity(self, c: str, j: str, ag: str, bJ: str) -> bool:
  if not self.owns_identity(c, bJ):
   return False
  return self.is_verified(c, j, ag)
 @gl.public.view
 def get_stats(self) -> str:
  return json.dumps({
  "total_verifications": int(self.H),
  "resolved": int(self.G),
  "pending": int(self.z),
  "stalled": int(self.ac),
  "identities_registered": int(self.P),
  "users_verified": int(self.V),
  "skills_verified": int(self.R),
  "pairs_verified": int(self.W),
  "fees_collected": str(int(self.M)),
  "fees_withdrawn": str(int(self.N)),
  "total_refunded": str(int(self.X)),
  "next_id": int(self.aU),
  })
 @gl.public.view
 def get_config(self) -> str:
  return json.dumps({
  "owner": str(self.O),
  "paused": bool(self.aT),
  "fee": str(int(self.aV)),
  "max_fee": str(bs),
  "cooldown_seconds": int(self.T),
  "resolve_window_seconds": int(self.u),
  "freshness_window_seconds": int(self.C),
  "levels": list(bK),
  "axis_values": list(by),
  "identity_binding": "register_identity",
  "statuses": [aR, ai, U],
  "thresholds": {
  "EXPERT": {"repos": bg, "bytes": bh},
  "PROFICIENT": {"repos": aC, "bytes": aD},
  "BEGINNER": {"repos": aQ, "bytes": 0},
  },
  "bytes_basis": bB,
  "max_username_length": S,
  "max_skill_length": ar,
  "max_page": aY,
  "repos_scanned_per_verification": bz,
  "forks_counted": False,
  "source": bd,
  })
 @gl.public.view
 def get_latest(self, c: str, j: str) -> str:
  a = self.I(c, j)
  bb = f(c)
  br = l(j)
  if a is None:
   return json.dumps({
   "found": False,
   "github_username": bb,
   "skill": br,
   "identity_owner": self.J(bb),
   "pending_id": self.aP(bb + "\x1f" + br),
   })
  aF = self.aZ(a)
  aF["found"] = True
  aF["fresh"] = self.bq(a)
  aF["pending_id"] = self.aP(bb + "\x1f" + br)
  return json.dumps(aF)
 def I(self, c: str, j: str):
  bS = g(self.al.get(self.aN(c, j)), 0)
  if bS <= 0:
   return None
  return self.ab.get(u32(bS))
 def bq(self, a) -> bool:
  cN = int(self.C)
  if cN <= 0:
   return True
  p = int(a.p)
  if p <= 0:
   return False
  aW = self.cb()
  if aW <= p:
   return True
  return (aW - p) <= cN
 def F(self) -> None:
  if gl.message.sender_address != self.O:
   raise gl.vm.UserError("owner only")
 @gl.public.write
 def set_fee(self, cT: int) -> str:
  self.F()
  n = g(cT, -1)
  if n < 0 or n > bs:
   raise gl.vm.UserError("fee must be between 0 and " + str(bs))
  self.aV = u128(n)
  return json.dumps({"ok": True, "fee": str(n)})
 @gl.public.write
 def set_cooldown(self, aX: int) -> str:
  self.F()
  n = g(aX, -1)
  if n < 0 or n > bi:
   raise gl.vm.UserError("cooldown must be between 0 and " + str(bi))
  self.T = u64(n)
  return json.dumps({"ok": True, "cooldown_seconds": n})
 @gl.public.write
 def set_resolve_window(self, aX: int) -> str:
  self.F()
  n = g(aX, -1)
  if n < at or n > au:
   raise gl.vm.UserError(
   "resolve window must be between " + str(at) + " and " + str(au),
   )
  self.u = u64(n)
  return json.dumps({"ok": True, "resolve_window_seconds": n})
 @gl.public.write
 def set_freshness_window(self, aX: int) -> str:
  self.F()
  n = g(aX, -1)
  if n < 0 or n > bc:
   raise gl.vm.UserError("freshness window must be between 0 and " + str(bc))
  self.C = u64(n)
  return json.dumps({"ok": True, "freshness_window_seconds": n})
 @gl.public.write
 def pause(self) -> str:
  self.F()
  self.aT = True
  return json.dumps({"ok": True, "paused": True})
 @gl.public.write
 def unpause(self) -> str:
  self.F()
  self.aT = False
  return json.dumps({"ok": True, "paused": False})
 @gl.public.write
 def transfer_ownership(self, cO: str) -> str:
  self.F()
  bY = v(cO).strip()
  if len(bY) != 42 or not bY.lower().startswith("0x"):
   raise gl.vm.UserError("new_owner must be a 0x-prefixed 20-byte address")
  if bY.lower() == ck:
   raise gl.vm.UserError("refusing to transfer ownership to the zero address")
  try:
   bm = Address(bY)
  except Exception:
   raise gl.vm.UserError("new_owner is not a valid address")
  self.O = bm
  return json.dumps({"ok": True, "owner": str(bm)})
 @gl.public.write
 def withdraw_fees(self, bR: int) -> str:
  self.F()
  cI = r(int(self.M) - int(self.N), 0, (1 << 128) - 1)
  n = g(bR, 0)
  if n <= 0:
   n = cI
  if n > cI:
   raise gl.vm.UserError("only " + str(cI) + " in fees is withdrawable")
  if n <= 0:
   raise gl.vm.UserError("no fees to withdraw")
  self.N = u128(int(self.N) + n)
  self.cQ(self.O, n)
  return json.dumps({"ok": True, "withdrawn": str(n), "remaining": str(cI - n)})
