# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
from dataclasses import dataclass
import json
aq = "EXPERT"
Y = "PROFICIENT"
af = "BEGINNER"
aa = "NONE"
bC = (aa, af, Y, aq)
aW = 5
aX = 1000
ar = 3
at = 500
aH = 1
U = "NO_SUCH_USER"
j = "UNAVAILABLE"
bq = (aq, Y, af, aa, U, j)
aI = "PENDING"
ab = "RESOLVED"
Q = "STALLED"
bm = (ab, Q)
O = 39
aj = 40
am = 3
an = 100
br = 100
bn = 100
bs = 0
bj = 10**18
bw = 300
aY = 86400
aF = 3600
ak = 60
al = 30 * 86400
bo = 0
aS = 365 * 86400
aP = 50
ac = 1000
bt = "github_repo_size_kb"
aT = "https://api.github.com/search/repositories"
ca = "0x0000000000000000000000000000000000000000"
ct = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
da = "0123456789ABCDEF"
def f(value, cb: int) -> int:
 try:
  if isinstance(value, bool):
   return cb
  return int(value)
 except Exception:
  return cb
def v(value) -> str:
 if value is None:
  return ""
 if isinstance(value, str):
  return value
 try:
  return str(value)
 except Exception:
  return ""
def t(value: int, db: int, cL: int) -> int:
 if value < db:
  return db
 if value > cL:
  return cL
 return value
def bx(y: int, m: int, d: int) -> int:
 y -= 1 if m <= 2 else 0
 dc = (y if y >= 0 else y - 399) // 400
 cM = y - dc * 400
 dm = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
 dn = cM * 365 + cM // 4 - cM // 100 + dm
 return dc * 146097 + dn - 719468
def bD(value: str) -> int:
 if not isinstance(value, str) or len(value) < 19:
  return 0
 try:
  df = int(value[0:4])
  cu = int(value[5:7])
  cN = int(value[8:10])
  cO = int(value[11:13])
  cA = int(value[14:16])
  cB = int(value[17:19])
 except Exception:
  return 0
 if cu < 1 or cu > 12 or cN < 1 or cN > 31:
  return 0
 if cO > 23 or cA > 59 or cB > 60:
  return 0
 return bx(df, cu, cN) * 86400 + cO * 3600 + cA * 60 + cB
def dg(text: str) -> str:
 if not isinstance(text, str):
  return ""
 if text == "":
  return ""
 h = 0xCBF29CE484222325
 for cc in text.encode("utf-8"):
  h = ((h ^ cc) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
 return "%016x" % h
def bX(L: str, g: str, z: str, r: int, n: int) -> str:
 cW = [
 l(L),
 k(g),
 v(z),
 str(f(r, 0)),
 str(f(n, 0)),
 ]
 return dg("\x1f".join(cW))
def l(value) -> str:
 text = v(value).strip()
 return text.lower()[:O]
def k(value) -> str:
 return " ".join(v(value).split()).lower()[:aj]
def bR(value) -> str:
 return " ".join(v(value).split())[:aj]
def bp(value) -> str:
 text = v(value).strip()
 if text == "":
  return "github_username is empty"
 if len(text) > O:
  return "github_username exceeds " + str(O) + " characters"
 bk = text.lower()
 for ch in bk:
  if not (("a" <= ch <= "z") or ("0" <= ch <= "9") or ch == "-"):
   return "github_username may only contain letters, digits and hyphens"
 if bk.startswith("-") or bk.endswith("-"):
  return "github_username may not start or end with a hyphen"
 if bk.find("--") >= 0:
  return "github_username may not contain consecutive hyphens"
 return ""
def bS(value) -> str:
 text = v(value)
 aZ = " ".join(text.split())
 if aZ == "":
  return "skill is empty"
 if len(aZ) > aj:
  return "skill exceeds " + str(aj) + " characters"
 for ch in aZ.lower():
  ok = ("a" <= ch <= "z") or ("0" <= ch <= "9") or ch in " +#-._"
  if not ok:
   return "skill may only contain letters, digits, spaces and + # - . _"
 return ""
def cP(value: str) -> str:
 if not isinstance(value, str):
  return ""
 cQ = []
 for cc in value.encode("utf-8"):
  ch = chr(cc)
  if ch in ct:
   cQ.append(ch)
  else:
   cQ.append("%" + da[(cc >> 4) & 0xF] + da[cc & 0xF])
 return "".join(cQ)
def cn(L: str, g: str) -> str:
 bT = cP(l(L))
 ba = cP(k(g))
 q = "user:" + bT + "%20language:%22" + ba + "%22"
 return aT + "?per_page=" + str(br) + "&sort=updated&q=" + q
def bl(z) -> int:
 text = v(z)
 for i in range(len(bC)):
  if bC[i] == text:
   return i
 return -1
def bE(r: int, n: int) -> str:
 bF = f(r, 0)
 cv = f(n, 0)
 if bF >= aW and cv >= aX:
  return aq
 if bF >= ar and cv >= at:
  return Y
 if bF >= aH:
  return af
 return aa
def cR(ag, g: str) -> dict:
 ba = k(g)
 if not isinstance(ag, dict):
  return {"ok": False, "repo_count": 0, "total_bytes": 0, "index_count": 0, "top_repos": [], "level": aa}
 cw = ag.get("items")
 if not isinstance(cw, list):
  cw = []
 aJ = []
 bG = 0
 for bY in cw[:bn]:
  if not isinstance(bY, dict):
   continue
  if k(bY.get("language")) != ba:
   continue
  ah = bY.get("size", 0)
  if isinstance(ah, bool) or not isinstance(ah, int):
   ah = 0
  ah = t(int(ah), 0, 1 << 40)
  cd = v(bY.get("name"))[:an]
  aJ.append({"name": cd, "bytes": ah * 1024})
  bG += ah * 1024
 aJ.sort(key=lambda au: (-au["bytes"], au["name"]))
 return {
 "ok": True,
 "repo_count": len(aJ),
 "total_bytes": bG,
 "index_count": t(f(ag.get("total_count", 0), 0), 0, 1 << 40),
 "incomplete": bool(ag.get("incomplete_results", False)),
 "top_repos": [au["name"] for au in aJ[:am]],
 "level": bE(len(aJ), bG),
 }
def bV(bb) -> int:
 if bb is None:
  return 0
 try:
  return len(bb)
 except Exception:
  return 0
def bW(do) -> list:
 text = v(do)
 if text == "":
  return []
 try:
  bc = json.loads(text)
 except Exception:
  return []
 if not isinstance(bc, list):
  return []
 return [v(cd)[:an] for cd in bc[:am]]
def cx(bH) -> int:
 s = getattr(bH, "status_code", None)
 if s is None:
  s = getattr(bH, "status", None)
 if s is None:
  return 0
 return f(s, 0)
def cG(bH) -> str:
 b = getattr(bH, "body", None)
 if b is None:
  b = getattr(bH, "text", None)
 if b is None:
  return ""
 if isinstance(b, bytes):
  return b.decode("utf-8", errors="ignore")
 return v(b)
def cC(L: str, g: str) -> dict:
 dd = cn(L, g)
 try:
  try:
   bH = gl.nondet.web.request(dd, method="GET")
  except AttributeError:
   bH = gl.nondet.web.get(dd)
  status = cx(bH)
  body = cG(bH)
 except Exception as dp:
  return {"axis": j, "status": 0, "reason": "fetch failed: " + v(dp)[:160]}
 if status == 422:
  return {"axis": U, "status": status, "reason": "GitHub cannot search this user"}
 if status != 200:
  return {"axis": j, "status": status, "reason": "GitHub answered " + str(status)}
 try:
  ag = json.loads(body)
 except Exception:
  return {"axis": j, "status": status, "reason": "response was not JSON"}
 av = cR(ag, g)
 if not av["ok"]:
  return {"axis": j, "status": status, "reason": "response had no items array"}
 return {
 "axis": av["level"],
 "status": status,
 "repo_count": av["repo_count"],
 "total_bytes": av["total_bytes"],
 "index_count": av["index_count"],
 "incomplete": av["incomplete"],
 "top_repos": av["top_repos"],
 "reason": "",
 }
def ce(aw) -> str:
 if not isinstance(aw, dict):
  return j
 ao = v(aw.get("axis"))
 if ao in bq:
  return ao
 return j
def bd(aw) -> str:
 ao = ce(aw)
 if bl(ao) < 0:
  return ao
 if not isinstance(aw, dict):
  return j
 bF = f(aw.get("repo_count"), -1)
 cv = f(aw.get("total_bytes"), -1)
 return ao + "\x1f" + str(bF) + "\x1f" + str(cv)
def az(L: str, g: str) -> dict:
 bT = str(L)
 ba = str(g)
 def leader_fn() -> dict:
  return cC(bT, ba)
 def validator_fn(aU: gl.vm.Result) -> bool:
  if not isinstance(aU, gl.vm.Return):
   leader_fn()
   return False
  dh = bd(leader_fn())
  cS = bd(aU.calldata)
  return dh == cS
 A = gl.vm.run_nondet(leader_fn, validator_fn)
 if not isinstance(A, dict):
  return {"axis": j, "status": 0, "reason": "nondet returned no document"}
 return A
@allow_storage
@dataclass
class Verification:
 c: u32
 e: str
 ax: str
 g: str
 aV: str
 status: str
 z: str
 r: u32
 n: u128
 M: u32
 aA: str
 H: str
 p: u64
 bu: Address
 ad: u64
 u: u64
 cf: u128
 be: u128
 bv: str
 G: u32
 ap: bool
 Z: bool
 w: str
 V: u32
@gl.evm.contract_interface
class _Payee:
 class View:
  pass
 class Write:
  pass
class SkillVerify(gl.Contract):
 bI: Address
 bf: bool
 W: TreeMap[u32, Verification]
 by: DynArray[u32]
 aK: u32
 cJ: TreeMap[str, DynArray[u32]]
 cp: TreeMap[str, DynArray[u32]]
 cg: TreeMap[str, DynArray[u32]]
 ae: TreeMap[str, u32]
 bz: TreeMap[str, u32]
 aB: TreeMap[Address, u64]
 aL: u128
 P: u64
 u: u64
 B: u64
 E: u32
 R: u32
 N: u32
 S: u32
 D: u32
 X: u32
 x: u32
 I: u128
 J: u128
 T: u128
 def __init__(self, aL: int = bs):
  self.bI = gl.message.sender_address
  self.bf = False
  self.aK = u32(1)
  self.aL = u128(t(f(aL, bs), 0, bj))
  self.P = u64(bw)
  self.u = u64(aF)
  self.B = u64(bo)
  self.E = u32(0)
  self.R = u32(0)
  self.N = u32(0)
  self.S = u32(0)
  self.D = u32(0)
  self.X = u32(0)
  self.x = u32(0)
  self.I = u128(0)
  self.J = u128(0)
  self.T = u128(0)
 def ci(self) -> int:
  return bD(gl.message_raw.get("datetime", ""))
 def cH(self, to: Address, bJ: int) -> None:
  if bJ <= 0:
   return
  _Payee(Address(str(to))).emit_transfer(value=u256(int(bJ)))
 def ai(self, K: Address, value: int, bg: str) -> str:
  if value > 0:
   self.cH(K, value)
   self.T = u128(t(int(self.T) + value, 0, (1 << 128) - 1))
  return json.dumps({"ok": False, "reason": bg, "refunded": str(value)})
 def aC(self, L: str, g: str) -> str:
  return l(L) + "\x1f" + k(g)
 def cy(self, c: int):
  return self.W.get(u32(t(f(c, -1), 0, (1 << 32) - 1)))
 def cj(self, a) -> bool:
  if a is None:
   return False
  return str(a.status) not in bm
 def ck(self, key: str, cX, c: int) -> bool:
  bb = cX.get_or_insert_default(key)
  cY = len(bb) == 0
  bb.append(u32(c))
  return cY
 def aD(self, co: int) -> int:
  return t(co + 1, 0, (1 << 32) - 1)
 def aQ(self, a) -> dict:
  aM = self.ci()
  p = int(a.p)
  de = (aM - p) if (p > 0 and aM > p) else 0
  return {
  "verification_id": int(a.c),
  "github_username": str(a.e),
  "username_display": str(a.ax),
  "skill": str(a.g),
  "skill_display": str(a.aV),
  "status": str(a.status),
  "level": str(a.z),
  "level_rank": bl(str(a.z)),
  "repo_count": int(a.r),
  "total_bytes": str(int(a.n)),
  "bytes_basis": str(a.bv),
  "index_count": int(a.M),
  "top_repos": bW(str(a.aA)),
  "content_hash": str(a.H),
  "verified_at": p,
  "verified_by": str(a.bu),
  "requested_at": int(a.ad),
  "age_seconds": de,
  "stale": bool(int(self.B) > 0 and p > 0 and de > int(self.B)),
  "resolve_window": int(a.u),
  "settle_stalled_at": int(a.ad) + int(a.u),
  "fee_paid": str(int(a.cf)),
  "fee_snapshot": str(int(a.be)),
  "attempts": int(a.G),
  "user_found": bool(a.ap),
  "incomplete_index": bool(a.Z),
  "last_reason": str(a.w),
  "http_status": int(a.V),
  }
 def cD(self, a, A: dict) -> dict:
  ao = ce(A)
  status_code = t(f(A.get("status"), 0), 0, (1 << 32) - 1)
  bg = v(A.get("reason"))[:200]
  if ao == j:
   a.G = u32(t(int(a.G) + 1, 0, ac))
   a.w = bg if bg else "source unavailable"
   a.V = u32(status_code)
   return {"resolved": False, "axis": ao, "reason": a.w}
  if ao == U:
   z = aa
   r = 0
   n = 0
   M = 0
   cT = []
   bK = False
   bL = False
  else:
   z = ao
   r = t(f(A.get("repo_count"), 0), 0, (1 << 32) - 1)
   n = t(f(A.get("total_bytes"), 0), 0, (1 << 128) - 1)
   M = t(f(A.get("index_count"), 0), 0, (1 << 32) - 1)
   cq = A.get("top_repos")
   cT = []
   if isinstance(cq, list):
    for cd in cq[:am]:
     cT.append(v(cd)[:an])
   bK = True
   bL = bool(A.get("incomplete", False))
   bM = bE(r, n)
   if bM != z:
    a.G = u32(t(int(a.G) + 1, 0, ac))
    a.w = (
    "incoherent result: level " + z + " with " + str(r)
    + " repos and " + str(n) + " bytes, which is " + bM
    )[:200]
    a.V = u32(status_code)
    return {"resolved": False, "axis": j,
    "incoherent": True, "reason": a.w}
  a.z = z
  a.r = u32(r)
  a.n = u128(n)
  a.M = u32(M)
  a.aA = json.dumps(cT)
  a.ap = bK
  a.Z = bL
  a.V = u32(status_code)
  a.w = bg
  a.G = u32(t(int(a.G) + 1, 0, ac))
  a.p = u64(t(self.ci(), 0, (1 << 64) - 1))
  a.H = bX(
  str(a.e), str(a.g), z, r, n,
  )
  a.status = ab
  return {"resolved": True, "axis": ao, "level": z}
 def bA(self, key: str) -> None:
  self.bz[key] = u32(0)
 def aG(self, key: str) -> int:
  return f(self.bz.get(key), 0) - 1
 def cI(self, bN, ay: int, bO: int) -> list:
  cZ = t(f(ay, 0), 0, 1 << 30)
  bZ = f(bO, aP)
  if bZ <= 0 or bZ > aP:
   bZ = aP
  if bN is None:
   return []
  aR = []
  bG = len(bN)
  i = bG - 1 - cZ
  while i >= 0 and len(aR) < bZ:
   a = self.W.get(u32(int(bN[i])))
   if a is not None:
    aR.append(self.aQ(a))
   i -= 1
  return aR
 @gl.public.write.payable
 def verify_skill(self, e: str, g: str) -> str:
  K = gl.message.sender_address
  value = f(gl.message.value, 0)
  if self.bf:
   return self.ai(K, value, "contract is paused")
  aN = bp(e)
  if aN:
   return self.ai(K, value, aN)
  aN = bS(g)
  if aN:
   return self.ai(K, value, aN)
  aL = int(self.aL)
  if value < aL:
   return self.ai(K, value, "fee is " + str(aL) + " and " + str(value) + " was sent")
  aM = self.ci()
  P = int(self.P)
  cU = f(self.aB.get(K), 0)
  if P > 0 and cU > 0 and aM > 0:
   cr = aM - cU
   if 0 <= cr < P:
    return self.ai(K, value, "rate limited, " + str(P - cr) + "s remaining")
  key = self.aC(e, g)
  cs = self.aG(key)
  if cs >= 0:
   return self.ai(
   K, value,
   "verification " + str(cs) + " for this username and skill is already in flight",
   )
  if int(self.aK) >= (1 << 32) - 1:
   return self.ai(K, value, "verification id space is exhausted")
  A = az(l(e), k(g))
  c = int(self.aK)
  self.aK = u32(c + 1)
  a = self.W.get_or_insert_default(u32(c))
  a.c = u32(c)
  a.e = l(e)
  a.ax = v(e).strip()[:O]
  a.g = k(g)
  a.aV = bR(g)
  a.status = aI
  a.z = ""
  a.r = u32(0)
  a.n = u128(0)
  a.M = u32(0)
  a.H = ""
  a.aA = "[]"
  a.p = u64(0)
  a.bu = K
  a.ad = u64(t(aM, 0, (1 << 64) - 1))
  a.u = u64(int(self.u))
  a.cf = u128(t(aL, 0, (1 << 128) - 1))
  a.be = u128(t(aL, 0, (1 << 128) - 1))
  a.bv = bt
  a.G = u32(0)
  a.ap = False
  a.Z = False
  a.w = ""
  a.V = u32(0)
  self.by.append(u32(c))
  if self.ck(a.e, self.cp, c):
   self.R = u32(self.aD(int(self.R)))
  if self.ck(a.g, self.cg, c):
   self.N = u32(self.aD(int(self.N)))
  if self.ck(key, self.cJ, c):
   self.S = u32(self.aD(int(self.S)))
  self.E = u32(self.aD(int(self.E)))
  self.aB[K] = u64(t(aM, 0, (1 << 64) - 1))
  self.I = u128(t(int(self.I) + aL, 0, (1 << 128) - 1))
  bU = self.cD(a, A)
  if bU["resolved"]:
   self.ae[key] = u32(c)
   self.D = u32(self.aD(int(self.D)))
   self.bA(key)
  else:
   self.bz[key] = u32(c + 1)
   self.x = u32(self.aD(int(self.x)))
  bP = value - aL
  if bP > 0:
   self.cH(K, bP)
  return json.dumps({
  "ok": True,
  "verification_id": c,
  "status": str(a.status),
  "level": str(a.z),
  "repo_count": int(a.r),
  "total_bytes": str(int(a.n)),
  "top_repos": bW(str(a.aA)),
  "content_hash": str(a.H),
  "user_found": bool(a.ap),
  "reason": str(a.w),
  "change_returned": str(bP if bP > 0 else 0),
  })
 @gl.public.write
 def resolve_pending(self, c: int) -> str:
  a = self.cy(c)
  if a is None:
   return json.dumps({"ok": False, "reason": "unknown verification_id"})
  if not self.cj(a):
   return json.dumps({
   "ok": False,
   "reason": "verification is " + str(a.status) + " and can never change",
   "status": str(a.status),
   "level": str(a.z),
   })
  if int(a.G) >= ac:
   return json.dumps({"ok": False, "reason": "attempt ceiling reached, settle it stalled"})
  key = self.aC(str(a.e), str(a.g))
  A = az(str(a.e), str(a.g))
  bU = self.cD(a, A)
  if bU["resolved"]:
   self.ae[key] = u32(int(a.c))
   self.D = u32(self.aD(int(self.D)))
   self.x = u32(t(int(self.x) - 1, 0, (1 << 32) - 1))
   self.bA(key)
  return json.dumps({
  "ok": True,
  "verification_id": int(a.c),
  "status": str(a.status),
  "level": str(a.z),
  "repo_count": int(a.r),
  "total_bytes": str(int(a.n)),
  "content_hash": str(a.H),
  "attempts": int(a.G),
  "reason": str(a.w),
  })
 @gl.public.write
 def settle_stalled(self, c: int) -> str:
  a = self.cy(c)
  if a is None:
   return json.dumps({"ok": False, "reason": "unknown verification_id"})
  if not self.cj(a):
   return json.dumps({
   "ok": False,
   "reason": "verification is already " + str(a.status),
   "status": str(a.status),
   })
  aM = self.ci()
  cV = int(a.ad) + int(a.u)
  if aM < cV:
   return json.dumps({
   "ok": False,
   "reason": "resolution window has " + str(cV - aM) + "s left",
   "settle_stalled_at": cV,
   })
  key = self.aC(str(a.e), str(a.g))
  a.status = Q
  a.z = ""
  a.w = "unresolved after " + str(int(a.u)) + "s"
  a.H = ""
  self.X = u32(self.aD(int(self.X)))
  self.x = u32(t(int(self.x) - 1, 0, (1 << 32) - 1))
  self.bA(key)
  return json.dumps({
  "ok": True,
  "verification_id": int(a.c),
  "status": Q,
  "reason": str(a.w),
  })
 @gl.public.view
 def get_verification(self, c: int) -> str:
  a = self.cy(c)
  if a is None:
   return json.dumps({"found": False, "verification_id": f(c, -1)})
  au = self.aQ(a)
  au["found"] = True
  return json.dumps(au)
 @gl.public.view
 def get_verifications_by_user(self, e: str, ay: int, bO: int) -> str:
  bT = l(e)
  bN = self.cp.get(bT)
  aR = self.cI(bN, ay, bO)
  return json.dumps({
  "github_username": bT,
  "total": bV(bN),
  "returned": len(aR),
  "offset": t(f(ay, 0), 0, 1 << 30),
  "verifications": aR,
  })
 @gl.public.view
 def get_verifications_by_skill(self, g: str, ay: int, bO: int) -> str:
  ba = k(g)
  bN = self.cg.get(ba)
  aR = self.cI(bN, ay, bO)
  return json.dumps({
  "skill": ba,
  "total": bV(bN),
  "returned": len(aR),
  "offset": t(f(ay, 0), 0, 1 << 30),
  "verifications": aR,
  })
 @gl.public.view
 def is_verified(self, e: str, g: str, aE: str) -> bool:
  cl = bl(aE)
  if cl < 0:
   return False
  a = self.F(e, g)
  if a is None:
   return False
  if not self.bh(a):
   return False
  return bl(str(a.z)) >= cl
 @gl.public.view
 def require_verified(self, e: str, g: str, aE: str) -> str:
  cl = bl(aE)
  if cl < 0:
   raise gl.vm.UserError("min_level must be one of " + ", ".join(bC))
  a = self.F(e, g)
  if a is None:
   raise gl.vm.UserError(
   "no resolved verification for " + l(e)
   + " / " + k(g),
   )
  if not self.bh(a):
   raise gl.vm.UserError("verification " + str(int(a.c)) + " is stale")
  di = bl(str(a.z))
  if di < cl:
   raise gl.vm.UserError(
   l(e) + " is " + str(a.z)
   + " in " + k(g) + ", " + str(aE) + " required",
   )
  au = self.aQ(a)
  au["ok"] = True
  return json.dumps(au)
 @gl.public.view
 def get_stats(self) -> str:
  return json.dumps({
  "total_verifications": int(self.E),
  "resolved": int(self.D),
  "pending": int(self.x),
  "stalled": int(self.X),
  "users_verified": int(self.R),
  "skills_verified": int(self.N),
  "pairs_verified": int(self.S),
  "fees_collected": str(int(self.I)),
  "fees_withdrawn": str(int(self.J)),
  "total_refunded": str(int(self.T)),
  "next_id": int(self.aK),
  })
 @gl.public.view
 def get_config(self) -> str:
  return json.dumps({
  "owner": str(self.bI),
  "paused": bool(self.bf),
  "fee": str(int(self.aL)),
  "max_fee": str(bj),
  "cooldown_seconds": int(self.P),
  "resolve_window_seconds": int(self.u),
  "freshness_window_seconds": int(self.B),
  "levels": list(bC),
  "axis_values": list(bq),
  "statuses": [aI, ab, Q],
  "thresholds": {
  "EXPERT": {"repos": aW, "bytes": aX},
  "PROFICIENT": {"repos": ar, "bytes": at},
  "BEGINNER": {"repos": aH, "bytes": 0},
  },
  "bytes_basis": bt,
  "max_username_length": O,
  "max_skill_length": aj,
  "max_page": aP,
  "repos_scanned_per_verification": br,
  "forks_counted": False,
  "source": aT,
  })
 @gl.public.view
 def get_latest(self, e: str, g: str) -> str:
  a = self.F(e, g)
  bB = l(e)
  bi = k(g)
  if a is None:
   return json.dumps({
   "found": False,
   "github_username": bB,
   "skill": bi,
   "pending_id": self.aG(bB + "\x1f" + bi),
   })
  au = self.aQ(a)
  au["found"] = True
  au["fresh"] = self.bh(a)
  au["pending_id"] = self.aG(bB + "\x1f" + bi)
  return json.dumps(au)
 def F(self, e: str, g: str):
  bK = f(self.ae.get(self.aC(e, g)), 0)
  if bK <= 0:
   return None
  return self.W.get(u32(bK))
 def bh(self, a) -> bool:
  cE = int(self.B)
  if cE <= 0:
   return True
  p = int(a.p)
  if p <= 0:
   return False
  aM = self.ci()
  if aM <= p:
   return True
  return (aM - p) <= cE
 def C(self) -> None:
  if gl.message.sender_address != self.bI:
   raise gl.vm.UserError("owner only")
 @gl.public.write
 def set_fee(self, cK: int) -> str:
  self.C()
  o = f(cK, -1)
  if o < 0 or o > bj:
   raise gl.vm.UserError("fee must be between 0 and " + str(bj))
  self.aL = u128(o)
  return json.dumps({"ok": True, "fee": str(o)})
 @gl.public.write
 def set_cooldown(self, aO: int) -> str:
  self.C()
  o = f(aO, -1)
  if o < 0 or o > aY:
   raise gl.vm.UserError("cooldown must be between 0 and " + str(aY))
  self.P = u64(o)
  return json.dumps({"ok": True, "cooldown_seconds": o})
 @gl.public.write
 def set_resolve_window(self, aO: int) -> str:
  self.C()
  o = f(aO, -1)
  if o < ak or o > al:
   raise gl.vm.UserError(
   "resolve window must be between " + str(ak) + " and " + str(al),
   )
  self.u = u64(o)
  return json.dumps({"ok": True, "resolve_window_seconds": o})
 @gl.public.write
 def set_freshness_window(self, aO: int) -> str:
  self.C()
  o = f(aO, -1)
  if o < 0 or o > aS:
   raise gl.vm.UserError("freshness window must be between 0 and " + str(aS))
  self.B = u64(o)
  return json.dumps({"ok": True, "freshness_window_seconds": o})
 @gl.public.write
 def pause(self) -> str:
  self.C()
  self.bf = True
  return json.dumps({"ok": True, "paused": True})
 @gl.public.write
 def unpause(self) -> str:
  self.C()
  self.bf = False
  return json.dumps({"ok": True, "paused": False})
 @gl.public.write
 def transfer_ownership(self, cF: str) -> str:
  self.C()
  bQ = v(cF).strip()
  if len(bQ) != 42 or not bQ.lower().startswith("0x"):
   raise gl.vm.UserError("new_owner must be a 0x-prefixed 20-byte address")
  if bQ.lower() == ca:
   raise gl.vm.UserError("refusing to transfer ownership to the zero address")
  try:
   bc = Address(bQ)
  except Exception:
   raise gl.vm.UserError("new_owner is not a valid address")
  self.bI = bc
  return json.dumps({"ok": True, "owner": str(bc)})
 @gl.public.write
 def withdraw_fees(self, bJ: int) -> str:
  self.C()
  cz = t(int(self.I) - int(self.J), 0, (1 << 128) - 1)
  o = f(bJ, 0)
  if o <= 0:
   o = cz
  if o > cz:
   raise gl.vm.UserError("only " + str(cz) + " in fees is withdrawable")
  if o <= 0:
   raise gl.vm.UserError("no fees to withdraw")
  self.J = u128(int(self.J) + o)
  self.cH(self.bI, o)
  return json.dumps({"ok": True, "withdrawn": str(o), "remaining": str(cz - o)})
