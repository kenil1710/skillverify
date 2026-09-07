# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
from dataclasses import dataclass
import json
ao = "EXPERT"
X = "PROFICIENT"
ad = "BEGINNER"
Z = "NONE"
bA = (Z, ad, X, ao)
aU = 5
aV = 1000
ap = 3
aq = 500
aF = 1
U = "NO_SUCH_USER"
p = "UNAVAILABLE"
bn = (ao, X, ad, Z, U, p)
aG = "PENDING"
aa = "RESOLVED"
Q = "STALLED"
bj = (aa, Q)
N = 39
ai = 40
al = 3
am = 100
bo = 100
bk = 100
bp = 0
bh = 10**18
bt = 300
aW = 86400
aD = 3600
aj = 60
ak = 30 * 86400
bl = 0
aQ = 365 * 86400
aN = 50
ar = 1000
bq = "github_repo_size_kb"
aR = "https://api.github.com/search/repositories"
bX = "0x0000000000000000000000000000000000000000"
cp = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
cY = "0123456789ABCDEF"
def k(value, bY: int) -> int:
 try:
  if isinstance(value, bool):
   return bY
  return int(value)
 except Exception:
  return bY
def v(value) -> str:
 if value is None:
  return ""
 if isinstance(value, str):
  return value
 try:
  return str(value)
 except Exception:
  return ""
def t(value: int, cZ: int, cI: int) -> int:
 if value < cZ:
  return cZ
 if value > cI:
  return cI
 return value
def bu(y: int, m: int, d: int) -> int:
 y -= 1 if m <= 2 else 0
 da = (y if y >= 0 else y - 399) // 400
 cJ = y - da * 400
 dk = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
 dl = cJ * 365 + cJ // 4 - cJ // 100 + dk
 return da * 146097 + dl - 719468
def bB(value: str) -> int:
 if not isinstance(value, str) or len(value) < 19:
  return 0
 try:
  dd = int(value[0:4])
  cq = int(value[5:7])
  cK = int(value[8:10])
  cL = int(value[11:13])
  cw = int(value[14:16])
  cx = int(value[17:19])
 except Exception:
  return 0
 if cq < 1 or cq > 12 or cK < 1 or cK > 31:
  return 0
 if cL > 23 or cw > 59 or cx > 60:
  return 0
 return bu(dd, cq, cK) * 86400 + cL * 3600 + cw * 60 + cx
def de(text: str) -> str:
 if not isinstance(text, str):
  return ""
 if text == "":
  return ""
 h = 0xCBF29CE484222325
 for bZ in text.encode("utf-8"):
  h = ((h ^ bZ) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
 return "%016x" % h
def bU(K: str, f: str, A: str, u: int, n: int) -> str:
 cU = [
 j(K),
 g(f),
 v(A),
 str(k(u, 0)),
 str(k(n, 0)),
 ]
 return de("\x1f".join(cU))
def j(value) -> str:
 text = v(value).strip()
 return text.lower()[:N]
def g(value) -> str:
 return " ".join(v(value).split()).lower()[:ai]
def bO(value) -> str:
 return " ".join(v(value).split())[:ai]
def bm(value) -> str:
 text = v(value).strip()
 if text == "":
  return "github_username is empty"
 if len(text) > N:
  return "github_username exceeds " + str(N) + " characters"
 bi = text.lower()
 for ch in bi:
  if not (("a" <= ch <= "z") or ("0" <= ch <= "9") or ch == "-"):
   return "github_username may only contain letters, digits and hyphens"
 if bi.startswith("-") or bi.endswith("-"):
  return "github_username may not start or end with a hyphen"
 if bi.find("--") >= 0:
  return "github_username may not contain consecutive hyphens"
 return ""
def bP(value) -> str:
 text = v(value)
 aX = " ".join(text.split())
 if aX == "":
  return "skill is empty"
 if len(aX) > ai:
  return "skill exceeds " + str(ai) + " characters"
 for ch in aX.lower():
  ok = ("a" <= ch <= "z") or ("0" <= ch <= "9") or ch in " +#-._"
  if not ok:
   return "skill may only contain letters, digits, spaces and + # - . _"
 return ""
def cM(value: str) -> str:
 if not isinstance(value, str):
  return ""
 cN = []
 for bZ in value.encode("utf-8"):
  ch = chr(bZ)
  if ch in cp:
   cN.append(ch)
  else:
   cN.append("%" + cY[(bZ >> 4) & 0xF] + cY[bZ & 0xF])
 return "".join(cN)
def cj(K: str, f: str) -> str:
 bQ = cM(j(K))
 aY = cM(g(f))
 q = "user:" + bQ + "%20language:%22" + aY + "%22"
 return aR + "?per_page=" + str(bo) + "&sort=updated&q=" + q
def bC(A) -> int:
 text = v(A)
 for i in range(len(bA)):
  if bA[i] == text:
   return i
 return -1
def bD(u: int, n: int) -> str:
 cr = k(u, 0)
 cO = k(n, 0)
 if cr >= aU and cO >= aV:
  return ao
 if cr >= ap and cO >= aq:
  return X
 if cr >= aF:
  return ad
 return Z
def cP(ae, f: str) -> dict:
 aY = g(f)
 if not isinstance(ae, dict):
  return {"ok": False, "repo_count": 0, "total_bytes": 0, "index_count": 0, "top_repos": [], "level": Z}
 cs = ae.get("items")
 if not isinstance(cs, list):
  cs = []
 aH = []
 bE = 0
 for bV in cs[:bk]:
  if not isinstance(bV, dict):
   continue
  if g(bV.get("language")) != aY:
   continue
  af = bV.get("size", 0)
  if isinstance(af, bool) or not isinstance(af, int):
   af = 0
  af = t(int(af), 0, 1 << 40)
  ca = v(bV.get("name"))[:am]
  aH.append({"name": ca, "bytes": af * 1024})
  bE += af * 1024
 aH.sort(key=lambda at: (-at["bytes"], at["name"]))
 return {
 "ok": True,
 "repo_count": len(aH),
 "total_bytes": bE,
 "index_count": t(k(ae.get("total_count", 0), 0), 0, 1 << 40),
 "incomplete": bool(ae.get("incomplete_results", False)),
 "top_repos": [at["name"] for at in aH[:al]],
 "level": bD(len(aH), bE),
 }
def bS(aZ) -> int:
 if aZ is None:
  return 0
 try:
  return len(aZ)
 except Exception:
  return 0
def bT(dm) -> list:
 text = v(dm)
 if text == "":
  return []
 try:
  ba = json.loads(text)
 except Exception:
  return []
 if not isinstance(ba, list):
  return []
 return [v(ca)[:am] for ca in ba[:al]]
def ct(bF) -> int:
 s = getattr(bF, "status_code", None)
 if s is None:
  s = getattr(bF, "status", None)
 if s is None:
  return 0
 return k(s, 0)
def cD(bF) -> str:
 b = getattr(bF, "body", None)
 if b is None:
  b = getattr(bF, "text", None)
 if b is None:
  return ""
 if isinstance(b, bytes):
  return b.decode("utf-8", errors="ignore")
 return v(b)
def cy(K: str, f: str) -> dict:
 db = cj(K, f)
 try:
  try:
   bF = gl.nondet.web.request(db, method="GET")
  except AttributeError:
   bF = gl.nondet.web.get(db)
  status = ct(bF)
  body = cD(bF)
 except Exception as dn:
  return {"axis": p, "status": 0, "reason": "fetch failed: " + v(dn)[:160]}
 if status == 422:
  return {"axis": U, "status": status, "reason": "GitHub cannot search this user"}
 if status != 200:
  return {"axis": p, "status": status, "reason": "GitHub answered " + str(status)}
 try:
  ae = json.loads(body)
 except Exception:
  return {"axis": p, "status": status, "reason": "response was not JSON"}
 au = cP(ae, f)
 if not au["ok"]:
  return {"axis": p, "status": status, "reason": "response had no items array"}
 return {
 "axis": au["level"],
 "status": status,
 "repo_count": au["repo_count"],
 "total_bytes": au["total_bytes"],
 "index_count": au["index_count"],
 "incomplete": au["incomplete"],
 "top_repos": au["top_repos"],
 "reason": "",
 }
def bv(cz) -> str:
 if not isinstance(cz, dict):
  return p
 bb = v(cz.get("axis"))
 if bb in bn:
  return bb
 return p
def ax(K: str, f: str) -> dict:
 bQ = str(K)
 aY = str(f)
 def leader_fn() -> dict:
  return cy(bQ, aY)
 def validator_fn(aS: gl.vm.Result) -> bool:
  if not isinstance(aS, gl.vm.Return):
   leader_fn()
   return False
  df = bv(leader_fn())
  cQ = bv(aS.calldata)
  return df == cQ
 x = gl.vm.run_nondet(leader_fn, validator_fn)
 if not isinstance(x, dict):
  return {"axis": p, "status": 0, "reason": "nondet returned no document"}
 return x
@allow_storage
@dataclass
class Verification:
 c: u32
 e: str
 av: str
 f: str
 aT: str
 status: str
 A: str
 u: u32
 n: u128
 L: u32
 ay: str
 G: str
 o: u64
 br: Address
 ab: u64
 r: u64
 cb: u128
 bc: u128
 bs: str
 O: u32
 an: bool
 Y: bool
 B: str
 ah: u32
@gl.evm.contract_interface
class _Payee:
 class View:
  pass
 class Write:
  pass
class SkillVerify(gl.Contract):
 bG: Address
 bd: bool
 V: TreeMap[u32, Verification]
 bw: DynArray[u32]
 aI: u32
 cG: TreeMap[str, DynArray[u32]]
 cl: TreeMap[str, DynArray[u32]]
 cc: TreeMap[str, DynArray[u32]]
 ac: TreeMap[str, u32]
 bx: TreeMap[str, u32]
 az: TreeMap[Address, u64]
 aJ: u128
 P: u64
 r: u64
 z: u64
 E: u32
 R: u32
 M: u32
 S: u32
 D: u32
 W: u32
 w: u32
 H: u128
 I: u128
 T: u128
 def __init__(self, aJ: int = bp):
  self.bG = gl.message.sender_address
  self.bd = False
  self.aI = u32(1)
  self.aJ = u128(t(k(aJ, bp), 0, bh))
  self.P = u64(bt)
  self.r = u64(aD)
  self.z = u64(bl)
  self.E = u32(0)
  self.R = u32(0)
  self.M = u32(0)
  self.S = u32(0)
  self.D = u32(0)
  self.W = u32(0)
  self.w = u32(0)
  self.H = u128(0)
  self.I = u128(0)
  self.T = u128(0)
 def cd(self) -> int:
  return bB(gl.message_raw.get("datetime", ""))
 def cE(self, to: Address, bH: int) -> None:
  if bH <= 0:
   return
  _Payee(Address(str(to))).emit_transfer(value=u256(int(bH)))
 def ag(self, J: Address, value: int, be: str) -> str:
  if value > 0:
   self.cE(J, value)
   self.T = u128(t(int(self.T) + value, 0, (1 << 128) - 1))
  return json.dumps({"ok": False, "reason": be, "refunded": str(value)})
 def aA(self, K: str, f: str) -> str:
  return j(K) + "\x1f" + g(f)
 def cu(self, c: int):
  return self.V.get(u32(t(k(c, -1), 0, (1 << 32) - 1)))
 def ce(self, a) -> bool:
  if a is None:
   return False
  return str(a.status) not in bj
 def cf(self, key: str, cV, c: int) -> bool:
  aZ = cV.get_or_insert_default(key)
  cW = len(aZ) == 0
  aZ.append(u32(c))
  return cW
 def aB(self, ck: int) -> int:
  return t(ck + 1, 0, (1 << 32) - 1)
 def aO(self, a) -> dict:
  aK = self.cd()
  o = int(a.o)
  dc = (aK - o) if (o > 0 and aK > o) else 0
  return {
  "verification_id": int(a.c),
  "github_username": str(a.e),
  "username_display": str(a.av),
  "skill": str(a.f),
  "skill_display": str(a.aT),
  "status": str(a.status),
  "level": str(a.A),
  "level_rank": bC(str(a.A)),
  "repo_count": int(a.u),
  "total_bytes": str(int(a.n)),
  "bytes_basis": str(a.bs),
  "index_count": int(a.L),
  "top_repos": bT(str(a.ay)),
  "content_hash": str(a.G),
  "verified_at": o,
  "verified_by": str(a.br),
  "requested_at": int(a.ab),
  "age_seconds": dc,
  "stale": bool(int(self.z) > 0 and o > 0 and dc > int(self.z)),
  "resolve_window": int(a.r),
  "settle_stalled_at": int(a.ab) + int(a.r),
  "fee_paid": str(int(a.cb)),
  "fee_snapshot": str(int(a.bc)),
  "attempts": int(a.O),
  "user_found": bool(a.an),
  "incomplete_index": bool(a.Y),
  "last_reason": str(a.B),
  "http_status": int(a.ah),
  }
 def cA(self, a, x: dict) -> dict:
  bb = bv(x)
  status_code = t(k(x.get("status"), 0), 0, (1 << 32) - 1)
  be = v(x.get("reason"))[:200]
  if bb == p:
   a.O = u32(t(int(a.O) + 1, 0, ar))
   a.B = be if be else "source unavailable"
   a.ah = u32(status_code)
   return {"resolved": False, "axis": bb, "reason": a.B}
  if bb == U:
   A = Z
   u = 0
   n = 0
   L = 0
   cR = []
   bI = False
   bJ = False
  else:
   A = bb
   u = t(k(x.get("repo_count"), 0), 0, (1 << 32) - 1)
   n = t(k(x.get("total_bytes"), 0), 0, (1 << 128) - 1)
   L = t(k(x.get("index_count"), 0), 0, (1 << 32) - 1)
   cm = x.get("top_repos")
   cR = []
   if isinstance(cm, list):
    for ca in cm[:al]:
     cR.append(v(ca)[:am])
   bI = True
   bJ = bool(x.get("incomplete", False))
   A = bD(u, n)
  a.A = A
  a.u = u32(u)
  a.n = u128(n)
  a.L = u32(L)
  a.ay = json.dumps(cR)
  a.an = bI
  a.Y = bJ
  a.ah = u32(status_code)
  a.B = be
  a.O = u32(t(int(a.O) + 1, 0, ar))
  a.o = u64(t(self.cd(), 0, (1 << 64) - 1))
  a.G = bU(
  str(a.e), str(a.f), A, u, n,
  )
  a.status = aa
  return {"resolved": True, "axis": bb, "level": A}
 def by(self, key: str) -> None:
  self.bx[key] = u32(0)
 def aE(self, key: str) -> int:
  return k(self.bx.get(key), 0) - 1
 def cF(self, bK, aw: int, bL: int) -> list:
  cX = t(k(aw, 0), 0, 1 << 30)
  bW = k(bL, aN)
  if bW <= 0 or bW > aN:
   bW = aN
  if bK is None:
   return []
  aP = []
  bE = len(bK)
  i = bE - 1 - cX
  while i >= 0 and len(aP) < bW:
   a = self.V.get(u32(int(bK[i])))
   if a is not None:
    aP.append(self.aO(a))
   i -= 1
  return aP
 @gl.public.write.payable
 def verify_skill(self, e: str, f: str) -> str:
  J = gl.message.sender_address
  value = k(gl.message.value, 0)
  if self.bd:
   return self.ag(J, value, "contract is paused")
  aL = bm(e)
  if aL:
   return self.ag(J, value, aL)
  aL = bP(f)
  if aL:
   return self.ag(J, value, aL)
  aJ = int(self.aJ)
  if value < aJ:
   return self.ag(J, value, "fee is " + str(aJ) + " and " + str(value) + " was sent")
  aK = self.cd()
  P = int(self.P)
  cS = k(self.az.get(J), 0)
  if P > 0 and cS > 0 and aK > 0:
   cn = aK - cS
   if 0 <= cn < P:
    return self.ag(J, value, "rate limited, " + str(P - cn) + "s remaining")
  key = self.aA(e, f)
  co = self.aE(key)
  if co >= 0:
   return self.ag(
   J, value,
   "verification " + str(co) + " for this username and skill is already in flight",
   )
  if int(self.aI) >= (1 << 32) - 1:
   return self.ag(J, value, "verification id space is exhausted")
  x = ax(j(e), g(f))
  c = int(self.aI)
  self.aI = u32(c + 1)
  a = self.V.get_or_insert_default(u32(c))
  a.c = u32(c)
  a.e = j(e)
  a.av = v(e).strip()[:N]
  a.f = g(f)
  a.aT = bO(f)
  a.status = aG
  a.A = ""
  a.u = u32(0)
  a.n = u128(0)
  a.L = u32(0)
  a.G = ""
  a.ay = "[]"
  a.o = u64(0)
  a.br = J
  a.ab = u64(t(aK, 0, (1 << 64) - 1))
  a.r = u64(int(self.r))
  a.cb = u128(t(aJ, 0, (1 << 128) - 1))
  a.bc = u128(t(aJ, 0, (1 << 128) - 1))
  a.bs = bq
  a.O = u32(0)
  a.an = False
  a.Y = False
  a.B = ""
  a.ah = u32(0)
  self.bw.append(u32(c))
  if self.cf(a.e, self.cl, c):
   self.R = u32(self.aB(int(self.R)))
  if self.cf(a.f, self.cc, c):
   self.M = u32(self.aB(int(self.M)))
  if self.cf(key, self.cG, c):
   self.S = u32(self.aB(int(self.S)))
  self.E = u32(self.aB(int(self.E)))
  self.az[J] = u64(t(aK, 0, (1 << 64) - 1))
  self.H = u128(t(int(self.H) + aJ, 0, (1 << 128) - 1))
  bR = self.cA(a, x)
  if bR["resolved"]:
   self.ac[key] = u32(c)
   self.D = u32(self.aB(int(self.D)))
   self.by(key)
  else:
   self.bx[key] = u32(c + 1)
   self.w = u32(self.aB(int(self.w)))
  bM = value - aJ
  if bM > 0:
   self.cE(J, bM)
  return json.dumps({
  "ok": True,
  "verification_id": c,
  "status": str(a.status),
  "level": str(a.A),
  "repo_count": int(a.u),
  "total_bytes": str(int(a.n)),
  "top_repos": bT(str(a.ay)),
  "content_hash": str(a.G),
  "user_found": bool(a.an),
  "reason": str(a.B),
  "change_returned": str(bM if bM > 0 else 0),
  })
 @gl.public.write
 def resolve_pending(self, c: int) -> str:
  a = self.cu(c)
  if a is None:
   return json.dumps({"ok": False, "reason": "unknown verification_id"})
  if not self.ce(a):
   return json.dumps({
   "ok": False,
   "reason": "verification is " + str(a.status) + " and can never change",
   "status": str(a.status),
   "level": str(a.A),
   })
  if int(a.O) >= ar:
   return json.dumps({"ok": False, "reason": "attempt ceiling reached, settle it stalled"})
  key = self.aA(str(a.e), str(a.f))
  x = ax(str(a.e), str(a.f))
  bR = self.cA(a, x)
  if bR["resolved"]:
   self.ac[key] = u32(int(a.c))
   self.D = u32(self.aB(int(self.D)))
   self.w = u32(t(int(self.w) - 1, 0, (1 << 32) - 1))
   self.by(key)
  return json.dumps({
  "ok": True,
  "verification_id": int(a.c),
  "status": str(a.status),
  "level": str(a.A),
  "repo_count": int(a.u),
  "total_bytes": str(int(a.n)),
  "content_hash": str(a.G),
  "attempts": int(a.O),
  "reason": str(a.B),
  })
 @gl.public.write
 def settle_stalled(self, c: int) -> str:
  a = self.cu(c)
  if a is None:
   return json.dumps({"ok": False, "reason": "unknown verification_id"})
  if not self.ce(a):
   return json.dumps({
   "ok": False,
   "reason": "verification is already " + str(a.status),
   "status": str(a.status),
   })
  aK = self.cd()
  cT = int(a.ab) + int(a.r)
  if aK < cT:
   return json.dumps({
   "ok": False,
   "reason": "resolution window has " + str(cT - aK) + "s left",
   "settle_stalled_at": cT,
   })
  key = self.aA(str(a.e), str(a.f))
  a.status = Q
  a.A = ""
  a.B = "unresolved after " + str(int(a.r)) + "s"
  a.G = ""
  self.W = u32(self.aB(int(self.W)))
  self.w = u32(t(int(self.w) - 1, 0, (1 << 32) - 1))
  self.by(key)
  return json.dumps({
  "ok": True,
  "verification_id": int(a.c),
  "status": Q,
  "reason": str(a.B),
  })
 @gl.public.view
 def get_verification(self, c: int) -> str:
  a = self.cu(c)
  if a is None:
   return json.dumps({"found": False, "verification_id": k(c, -1)})
  at = self.aO(a)
  at["found"] = True
  return json.dumps(at)
 @gl.public.view
 def get_verifications_by_user(self, e: str, aw: int, bL: int) -> str:
  bQ = j(e)
  bK = self.cl.get(bQ)
  aP = self.cF(bK, aw, bL)
  return json.dumps({
  "github_username": bQ,
  "total": bS(bK),
  "returned": len(aP),
  "offset": t(k(aw, 0), 0, 1 << 30),
  "verifications": aP,
  })
 @gl.public.view
 def get_verifications_by_skill(self, f: str, aw: int, bL: int) -> str:
  aY = g(f)
  bK = self.cc.get(aY)
  aP = self.cF(bK, aw, bL)
  return json.dumps({
  "skill": aY,
  "total": bS(bK),
  "returned": len(aP),
  "offset": t(k(aw, 0), 0, 1 << 30),
  "verifications": aP,
  })
 @gl.public.view
 def is_verified(self, e: str, f: str, aC: str) -> bool:
  cg = bC(aC)
  if cg < 0:
   return False
  a = self.F(e, f)
  if a is None:
   return False
  if not self.bf(a):
   return False
  return bC(str(a.A)) >= cg
 @gl.public.view
 def require_verified(self, e: str, f: str, aC: str) -> str:
  cg = bC(aC)
  if cg < 0:
   raise gl.vm.UserError("min_level must be one of " + ", ".join(bA))
  a = self.F(e, f)
  if a is None:
   raise gl.vm.UserError(
   "no resolved verification for " + j(e)
   + " / " + g(f),
   )
  if not self.bf(a):
   raise gl.vm.UserError("verification " + str(int(a.c)) + " is stale")
  dg = bC(str(a.A))
  if dg < cg:
   raise gl.vm.UserError(
   j(e) + " is " + str(a.A)
   + " in " + g(f) + ", " + str(aC) + " required",
   )
  at = self.aO(a)
  at["ok"] = True
  return json.dumps(at)
 @gl.public.view
 def get_stats(self) -> str:
  return json.dumps({
  "total_verifications": int(self.E),
  "resolved": int(self.D),
  "pending": int(self.w),
  "stalled": int(self.W),
  "users_verified": int(self.R),
  "skills_verified": int(self.M),
  "pairs_verified": int(self.S),
  "fees_collected": str(int(self.H)),
  "fees_withdrawn": str(int(self.I)),
  "total_refunded": str(int(self.T)),
  "next_id": int(self.aI),
  })
 @gl.public.view
 def get_config(self) -> str:
  return json.dumps({
  "owner": str(self.bG),
  "paused": bool(self.bd),
  "fee": str(int(self.aJ)),
  "max_fee": str(bh),
  "cooldown_seconds": int(self.P),
  "resolve_window_seconds": int(self.r),
  "freshness_window_seconds": int(self.z),
  "levels": list(bA),
  "axis_values": list(bn),
  "statuses": [aG, aa, Q],
  "thresholds": {
  "EXPERT": {"repos": aU, "bytes": aV},
  "PROFICIENT": {"repos": ap, "bytes": aq},
  "BEGINNER": {"repos": aF, "bytes": 0},
  },
  "bytes_basis": bq,
  "max_username_length": N,
  "max_skill_length": ai,
  "max_page": aN,
  "repos_scanned_per_verification": bo,
  "forks_counted": False,
  "source": aR,
  })
 @gl.public.view
 def get_latest(self, e: str, f: str) -> str:
  a = self.F(e, f)
  bz = j(e)
  bg = g(f)
  if a is None:
   return json.dumps({
   "found": False,
   "github_username": bz,
   "skill": bg,
   "pending_id": self.aE(bz + "\x1f" + bg),
   })
  at = self.aO(a)
  at["found"] = True
  at["fresh"] = self.bf(a)
  at["pending_id"] = self.aE(bz + "\x1f" + bg)
  return json.dumps(at)
 def F(self, e: str, f: str):
  bI = k(self.ac.get(self.aA(e, f)), 0)
  if bI <= 0:
   return None
  return self.V.get(u32(bI))
 def bf(self, a) -> bool:
  cB = int(self.z)
  if cB <= 0:
   return True
  o = int(a.o)
  if o <= 0:
   return False
  aK = self.cd()
  if aK <= o:
   return True
  return (aK - o) <= cB
 def C(self) -> None:
  if gl.message.sender_address != self.bG:
   raise gl.vm.UserError("owner only")
 @gl.public.write
 def set_fee(self, cH: int) -> str:
  self.C()
  l = k(cH, -1)
  if l < 0 or l > bh:
   raise gl.vm.UserError("fee must be between 0 and " + str(bh))
  self.aJ = u128(l)
  return json.dumps({"ok": True, "fee": str(l)})
 @gl.public.write
 def set_cooldown(self, aM: int) -> str:
  self.C()
  l = k(aM, -1)
  if l < 0 or l > aW:
   raise gl.vm.UserError("cooldown must be between 0 and " + str(aW))
  self.P = u64(l)
  return json.dumps({"ok": True, "cooldown_seconds": l})
 @gl.public.write
 def set_resolve_window(self, aM: int) -> str:
  self.C()
  l = k(aM, -1)
  if l < aj or l > ak:
   raise gl.vm.UserError(
   "resolve window must be between " + str(aj) + " and " + str(ak),
   )
  self.r = u64(l)
  return json.dumps({"ok": True, "resolve_window_seconds": l})
 @gl.public.write
 def set_freshness_window(self, aM: int) -> str:
  self.C()
  l = k(aM, -1)
  if l < 0 or l > aQ:
   raise gl.vm.UserError("freshness window must be between 0 and " + str(aQ))
  self.z = u64(l)
  return json.dumps({"ok": True, "freshness_window_seconds": l})
 @gl.public.write
 def pause(self) -> str:
  self.C()
  self.bd = True
  return json.dumps({"ok": True, "paused": True})
 @gl.public.write
 def unpause(self) -> str:
  self.C()
  self.bd = False
  return json.dumps({"ok": True, "paused": False})
 @gl.public.write
 def transfer_ownership(self, cC: str) -> str:
  self.C()
  bN = v(cC).strip()
  if len(bN) != 42 or not bN.lower().startswith("0x"):
   raise gl.vm.UserError("new_owner must be a 0x-prefixed 20-byte address")
  if bN.lower() == bX:
   raise gl.vm.UserError("refusing to transfer ownership to the zero address")
  try:
   ba = Address(bN)
  except Exception:
   raise gl.vm.UserError("new_owner is not a valid address")
  self.bG = ba
  return json.dumps({"ok": True, "owner": str(ba)})
 @gl.public.write
 def withdraw_fees(self, bH: int) -> str:
  self.C()
  cv = t(int(self.H) - int(self.I), 0, (1 << 128) - 1)
  l = k(bH, 0)
  if l <= 0:
   l = cv
  if l > cv:
   raise gl.vm.UserError("only " + str(cv) + " in fees is withdrawable")
  if l <= 0:
   raise gl.vm.UserError("no fees to withdraw")
  self.I = u128(int(self.I) + l)
  self.cE(self.bG, l)
  return json.dumps({"ok": True, "withdrawn": str(l), "remaining": str(cv - l)})
