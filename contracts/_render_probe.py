# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

# Throwaway diagnostic. Nothing in SkillVerify imports it. What survives the
# probe is docs/PROBE.md and the design decisions it forces.
#
# SkillVerify asks one question: does GitHub user U actually use language L, and
# how much? Every validator answers it independently by walking the GitHub REST
# API. Four things have to be true for that to work, and none of them can be
# assumed from documentation:
#
#   1. EGRESS. Can a validator reach api.github.com AT ALL? Unauthenticated
#      GitHub is metered at 60 requests/hour PER SOURCE IP, and every validator
#      in a round shares one datacentre range. The interesting failure is not a
#      403 on the first call, it is a 403 with `rate limit exceeded` on the
#      SECOND node, which would make the contract work in testing and fail in
#      production.
#
#   2. SHAPE. /users/{u}/repos and /repos/{o}/{r}/languages have to be read by
#      an extractor written against the real documents. Is `language` ever null?
#      Are fork repos in the list? Is the languages map keyed by display name
#      ("C", "Python") or by something else?
#
#   3. THE LOAD-BEARING ONE — DRIFT, AND ITS BUDGET. A verification resolves
#      when validators independently fetch. A repo list changes when the user
#      pushes; a languages map changes when a file lands. If nodes disagree on
#      the RAW BYTES, agreeing on raw bytes is off the table and the contract
#      must agree on a DERIVED LEVEL. `probe_drift` measures that per URL.
#
#   4. THE ONE THAT SIZES THE FAN-OUT — REQUEST BUDGET. Scoring one user means
#      1 repo-list call plus ONE CALL PER REPO. At 60/hour shared across every
#      validator, a 30-repo user costs 31 requests and two verifications in an
#      hour exhaust the quota for the whole network. `probe_budget` runs the
#      real fan-out at several widths and reports where it starts to 403, which
#      is what decides MAX_REPOS_SCANNED.
#
# Line 1 must stay the runner pin: a comment above it makes the contract
# undeployable and the only error reported is `invalid_contract`.

from genlayer import *

import json


def _status(res) -> int:
	s = getattr(res, "status_code", None)
	if s is None:
		s = getattr(res, "status", None)
	if s is None:
		return 0
	return int(s)


def _body(res) -> str:
	b = getattr(res, "body", None)
	if b is None:
		b = getattr(res, "text", None)
	if b is None:
		return ""
	if isinstance(b, bytes):
		return b.decode("utf-8", errors="ignore")
	return str(b)


def _fetch(url: str) -> tuple:
	"""(status, body). Tries web.request first and falls back to web.get: the
	prior projects split between the two spellings and the probe should not die
	on which one this runner build exposes."""
	try:
		res = gl.nondet.web.request(url, method="GET")
	except AttributeError:
		res = gl.nondet.web.get(url)
	return _status(res), _body(res)


def _describe(d, depth: int) -> dict:
	"""A shallow type map of a JSON document - enough to write an extractor
	against without dumping a whole repo list into storage."""
	out = {}
	if isinstance(d, list):
		return {"_list_len": len(d), "_first": _describe(d[0], depth - 1) if len(d) > 0 else "empty"}
	if not isinstance(d, dict):
		return {"_type": type(d).__name__, "_value": str(d)[:80]}
	for k in sorted(d.keys())[:40]:
		v = d[k]
		if isinstance(v, dict):
			if depth > 0:
				out[str(k)] = _describe(v, depth - 1)
			else:
				out[str(k)] = "dict{" + ",".join(sorted([str(x) for x in v.keys()])[:12]) + "}"
		elif isinstance(v, list):
			head = ""
			if len(v) > 0:
				if isinstance(v[0], dict):
					head = "dict{" + ",".join(sorted([str(x) for x in v[0].keys()])[:14]) + "}"
				else:
					head = str(v[:3])[:100]
			out[str(k)] = "list[" + str(len(v)) + "] " + head
		else:
			out[str(k)] = str(type(v).__name__) + "=" + str(v)[:80]
	return out


def _repo_names(body: str, limit: int) -> list:
	"""What the real scan reads out of /users/{u}/repos: (owner, name, primary
	language, fork flag) for each entry, in the order GitHub returned them."""
	try:
		doc = json.loads(body)
	except ValueError:
		return []
	if not isinstance(doc, list):
		return []
	out = []
	for entry in doc[:limit]:
		if not isinstance(entry, dict):
			continue
		owner = entry.get("owner")
		login = ""
		if isinstance(owner, dict):
			login = str(owner.get("login", ""))
		out.append({
			"owner": login,
			"name": str(entry.get("name", "")),
			"lang": str(entry.get("language")),
			"fork": bool(entry.get("fork", False)),
			"size": int(entry.get("size", 0) or 0),
		})
	return out


def _level(repo_count: int, total_bytes: int) -> str:
	"""The REAL scoring ladder, run inside the probe so the consensus axis being
	measured is the one the contract will actually put on it."""
	if repo_count >= 5 and total_bytes >= 1000:
		return "EXPERT"
	if repo_count >= 3 and total_bytes >= 500:
		return "PROFICIENT"
	if repo_count >= 1:
		return "BEGINNER"
	return "NONE"


class RenderProbe(gl.Contract):
	report: str
	url: str
	text: str
	text_len: u32

	def __init__(self):
		self.report = ""
		self.url = ""
		self.text = ""
		self.text_len = u32(0)

	@gl.public.write
	def probe_statuses(self, urls: list) -> None:
		"""HTTP status + body length for each plain GET, one transaction.

		Distinguishes 'blocked' from 'empty' from 'refused': a 403 is either an
		egress block or GitHub's shared-IP rate limit (the body says which), a
		200 with a 2-byte body is `[]` — a user with no repos — and a status of
		-1 with an exception string is the runner refusing the request before it
		went out. They call for different pivots."""
		targets = [str(u) for u in urls][:12]

		def leader_fn() -> dict:
			found = {}
			for u in targets:
				try:
					st, body = _fetch(u)
					found[u] = {"status": st, "len": len(body), "head": body[:240]}
				except Exception as e:
					found[u] = {"status": -1, "len": -1, "err": str(e)[:240]}
			return found

		def validator_fn(leader_result: gl.vm.Result) -> bool:
			# Shape only. Whether validators WOULD disagree is measured by
			# probe_drift, deliberately as its own experiment.
			return isinstance(leader_result, gl.vm.Return)

		self.report = json.dumps(gl.vm.run_nondet(leader_fn, validator_fn))

	@gl.public.write
	def probe_shape(self, url: str, depth: int) -> None:
		"""The document's SHAPE, which is what an extractor is written against."""
		d = int(depth)
		if d < 0 or d > 3:
			d = 2

		def leader_fn() -> dict:
			st, body = _fetch(url)
			out = {"status": st, "len": len(body)}
			try:
				doc = json.loads(body)
			except ValueError:
				out["err"] = "unparseable"
				out["head"] = body[:400]
				return out
			out["top"] = _describe(doc, d)
			return out

		def validator_fn(leader_result: gl.vm.Result) -> bool:
			return isinstance(leader_result, gl.vm.Return)

		self.report = json.dumps(gl.vm.run_nondet(leader_fn, validator_fn))

	@gl.public.write
	def probe_repos(self, username: str, limit: int) -> None:
		"""The repo list as the scan will read it: name, primary language, fork
		flag. Answers the two questions the ladder depends on — is `language`
		ever null, and are FORKS in the list (a user with 40 forked C repos
		would score EXPERT in C without writing a line of it)."""
		user = str(username)
		n = int(limit)
		if n <= 0 or n > 100:
			n = 100

		def leader_fn() -> dict:
			st, body = _fetch("https://api.github.com/users/" + user + "/repos?per_page=100&sort=updated")
			repos = _repo_names(body, n)
			forks = len([r for r in repos if r["fork"]])
			nulls = len([r for r in repos if r["lang"] == "None"])
			return {"status": st, "len": len(body), "count": len(repos), "forks": forks, "null_lang": nulls, "repos": repos[:30]}

		def validator_fn(leader_result: gl.vm.Result) -> bool:
			return isinstance(leader_result, gl.vm.Return)

		self.report = json.dumps(gl.vm.run_nondet(leader_fn, validator_fn))

	@gl.public.write
	def probe_drift(self, url: str) -> None:
		"""THE decisive experiment. The leader fetches the URL; every validator
		re-fetches the SAME url and compares the whole body EXACTLY.

		COMMITTED means independent nodes, seconds apart, read byte-identical
		documents. UNDETERMINED means the document moved under them and the
		design must agree on a derived verdict instead. Either answer is a
		result; assuming one is how the contract gets built on sand."""
		target = str(url)

		def leader_fn() -> dict:
			st, body = _fetch(target)
			return {"status": st, "len": len(body), "body": body[:4000]}

		def validator_fn(leader_result: gl.vm.Result) -> bool:
			if not isinstance(leader_result, gl.vm.Return):
				leader_fn()  # a leader error is RE-RUN, never answered False
				return False
			mine = leader_fn()
			theirs = leader_result.calldata
			return json.dumps(mine, sort_keys=True) == json.dumps(theirs, sort_keys=True)

		out = gl.vm.run_nondet(leader_fn, validator_fn)
		self.report = json.dumps({"agreed_exactly": True, "leader": out})

	@gl.public.write
	def probe_level(self, username: str, skill: str, max_repos: int) -> None:
		"""THE ONE THAT PROVES THE DESIGN.

		Runs the REAL scan — repo list, then one languages call per repo — and
		puts the resulting LEVEL STRING on the consensus axis, exactly as
		verify_skill will. Every validator re-runs the whole fan-out and
		agreement is judged on the level alone.

		This is the experiment that says whether SkillVerify is buildable. If
		EXPERT/PROFICIENT/BEGINNER/NONE survives independent re-execution across
		N+1 HTTP calls per node, the contract works. If it does not, no amount
		of contract logic saves it."""
		user = str(username)
		lang = str(skill)
		cap = int(max_repos)
		if cap <= 0 or cap > 50:
			cap = 12

		def leader_fn() -> dict:
			st, body = _fetch("https://api.github.com/users/" + user + "/repos?per_page=100&sort=updated")
			if st != 200:
				return {"ok": False, "status": st, "level": "ERROR", "calls": 1}
			repos = _repo_names(body, cap)
			calls = 1
			hits = 0
			total = 0
			tops = []
			errors = 0
			for r in repos:
				if r["owner"] == "" or r["name"] == "":
					continue
				st2, b2 = _fetch("https://api.github.com/repos/" + r["owner"] + "/" + r["name"] + "/languages")
				calls += 1
				if st2 != 200:
					errors += 1
					continue
				try:
					langs = json.loads(b2)
				except ValueError:
					errors += 1
					continue
				if not isinstance(langs, dict):
					continue
				for k in langs.keys():
					if str(k).lower() == lang.lower():
						n = langs[k]
						if isinstance(n, bool) or not isinstance(n, int):
							continue
						hits += 1
						total += int(n)
						tops.append({"repo": r["name"], "bytes": int(n)})
			tops.sort(key=lambda x: (-x["bytes"], x["repo"]))
			return {
				"ok": True,
				"level": _level(hits, total),
				"repo_count": hits,
				"total_bytes": total,
				"scanned": len(repos),
				"calls": calls,
				"errors": errors,
				"top": tops[:3],
			}

		def validator_fn(leader_result: gl.vm.Result) -> bool:
			if not isinstance(leader_result, gl.vm.Return):
				leader_fn()
				return False
			mine = leader_fn()
			theirs = leader_result.calldata
			# ONE axis: the level. Not the byte count, not the call count.
			return str(mine.get("level")) == str(theirs.get("level"))

		out = gl.vm.run_nondet(leader_fn, validator_fn)
		self.report = json.dumps({"level_agreed": True, "skill": lang, "user": user, "leader": out})

	@gl.public.write
	def probe_level_strict(self, username: str, skill: str, max_repos: int) -> None:
		"""The same scan with the WHOLE RESULT on the axis — level, repo count
		and byte total together.

		Run beside probe_level to price the difference. If this commits too,
		byte counts are stable across nodes and the contract may store them as
		measured. If only probe_level commits, the extra fields drift and
		storing them would make every verification UNDETERMINED for a reason
		that has nothing to do with the skill."""
		user = str(username)
		lang = str(skill)
		cap = int(max_repos)
		if cap <= 0 or cap > 50:
			cap = 12

		def leader_fn() -> dict:
			st, body = _fetch("https://api.github.com/users/" + user + "/repos?per_page=100&sort=updated")
			if st != 200:
				return {"ok": False, "level": "ERROR", "repo_count": 0, "total_bytes": 0}
			repos = _repo_names(body, cap)
			hits = 0
			total = 0
			for r in repos:
				if r["owner"] == "" or r["name"] == "":
					continue
				st2, b2 = _fetch("https://api.github.com/repos/" + r["owner"] + "/" + r["name"] + "/languages")
				if st2 != 200:
					continue
				try:
					langs = json.loads(b2)
				except ValueError:
					continue
				if not isinstance(langs, dict):
					continue
				for k in langs.keys():
					if str(k).lower() == lang.lower():
						n = langs[k]
						if isinstance(n, bool) or not isinstance(n, int):
							continue
						hits += 1
						total += int(n)
			return {"ok": True, "level": _level(hits, total), "repo_count": hits, "total_bytes": total}

		def validator_fn(leader_result: gl.vm.Result) -> bool:
			if not isinstance(leader_result, gl.vm.Return):
				leader_fn()
				return False
			mine = leader_fn()
			theirs = leader_result.calldata
			return json.dumps(mine, sort_keys=True) == json.dumps(theirs, sort_keys=True)

		out = gl.vm.run_nondet(leader_fn, validator_fn)
		self.report = json.dumps({"strict_agreed": True, "leader": out})

	@gl.public.write
	def probe_budget(self, username: str, calls: int) -> None:
		"""THE ONE THAT SIZES THE FAN-OUT.

		Fires N sequential languages calls from one node and reports the status
		of each. Unauthenticated GitHub allows 60/hour per source IP and every
		validator shares a datacentre range, so the number that matters is not
		'does one call work' but 'at which call does the 403 start'. That number
		is MAX_REPOS_SCANNED's ceiling."""
		user = str(username)
		n = int(calls)
		if n <= 0 or n > 60:
			n = 20

		def leader_fn() -> dict:
			st, body = _fetch("https://api.github.com/users/" + user + "/repos?per_page=100&sort=updated")
			repos = _repo_names(body, n)
			seq = []
			first_bad = -1
			for i in range(len(repos)):
				r = repos[i]
				if r["owner"] == "" or r["name"] == "":
					continue
				st2, b2 = _fetch("https://api.github.com/repos/" + r["owner"] + "/" + r["name"] + "/languages")
				seq.append({"i": i, "status": st2, "len": len(b2)})
				if st2 != 200 and first_bad < 0:
					first_bad = i
					seq.append({"i": i, "head": b2[:240]})
			return {"list_status": st, "n": len(seq), "first_bad": first_bad, "seq": seq}

		def validator_fn(leader_result: gl.vm.Result) -> bool:
			return isinstance(leader_result, gl.vm.Return)

		self.report = json.dumps(gl.vm.run_nondet(leader_fn, validator_fn))

	@gl.public.write
	def probe_get(self, url: str, start: int, count: int) -> None:
		"""Raw GET keeping a window of the body, for anything the structured
		probes render unreadable."""
		begin = int(start)
		span = int(count)
		if span <= 0 or span > 12000:
			span = 12000

		def leader_fn() -> dict:
			st, body = _fetch(url)
			return {"len": len(body), "status": st, "window": body[begin:begin + span]}

		def validator_fn(leader_result: gl.vm.Result) -> bool:
			return isinstance(leader_result, gl.vm.Return)

		out = gl.vm.run_nondet(leader_fn, validator_fn)
		self.url = str(url) + " [status " + str(out["status"]) + "]"
		self.text_len = u32(int(out["len"]))
		self.text = str(out["window"])

	@gl.public.write
	def probe_rate(self, url: str) -> None:
		"""GitHub's own accounting of the quota, from inside a validator.

		/rate_limit is EXEMPT from the limit it reports, so this can be called
		while the bucket is empty. Two numbers decide the whole design: `limit`
		(60 unauthenticated) and `remaining`. The axis carries `remaining`
		itself — if every validator reports the SAME remaining, they are behind
		ONE shared IP and a verification's cost is (calls x validators). If they
		report different numbers, each node has its own bucket and the fan-out
		is affordable after all. Nothing else distinguishes those two worlds,
		and they lead to opposite contracts."""
		target = str(url)

		def leader_fn() -> dict:
			st, body = _fetch(target)
			try:
				doc = json.loads(body)
			except ValueError:
				return {"status": st, "err": body[:200]}
			core = {}
			if isinstance(doc, dict):
				res = doc.get("resources")
				if isinstance(res, dict) and isinstance(res.get("core"), dict):
					core = res["core"]
				elif isinstance(doc.get("rate"), dict):
					core = doc["rate"]
			return {
				"status": st,
				"limit": int(core.get("limit", -1) or -1),
				"remaining": int(core.get("remaining", -1) or -1),
				"reset": int(core.get("reset", 0) or 0),
				"used": int(core.get("used", -1) or -1),
			}

		def validator_fn(leader_result: gl.vm.Result) -> bool:
			if not isinstance(leader_result, gl.vm.Return):
				leader_fn()
				return False
			mine = leader_fn()
			theirs = leader_result.calldata
			# The decisive comparison: same bucket or different buckets.
			return int(mine.get("remaining", -1)) == int(theirs.get("remaining", -1))

		out = gl.vm.run_nondet(leader_fn, validator_fn)
		self.report = json.dumps({"remaining_agreed": True, "leader": out})

	@gl.public.write
	def probe_level_onecall(self, username: str, skill: str) -> None:
		"""THE PIVOT CANDIDATE. The same ladder from ONE HTTP request.

		/users/{u}/repos already carries each repo's PRIMARY language and its
		`size` in KB. Reading only that costs 1 call per validator instead of
		1+N, which is the difference between ~12 verifications an hour across
		the whole network and two. The question this measures is whether the
		LEVEL it produces still survives independent re-execution, and whether
		it agrees with the fan-out answer for a user whose fan-out we already
		measured (torvalds/C -> EXPERT)."""
		user = str(username)
		lang = str(skill)

		def leader_fn() -> dict:
			st, body = _fetch("https://api.github.com/users/" + user + "/repos?per_page=100&sort=updated")
			if st != 200:
				return {"ok": False, "status": st, "level": "ERROR"}
			repos = _repo_names(body, 100)
			hits = 0
			total = 0
			own = 0
			tops = []
			for r in repos:
				if r["lang"].lower() != lang.lower():
					continue
				hits += 1
				if not r["fork"]:
					own += 1
				total += int(r["size"]) * 1024
				tops.append({"repo": r["name"], "bytes": int(r["size"]) * 1024, "fork": r["fork"]})
			tops.sort(key=lambda x: (-x["bytes"], x["repo"]))
			return {
				"ok": True,
				"level": _level(hits, total),
				"repo_count": hits,
				"own_count": own,
				"total_bytes": total,
				"listed": len(repos),
				"top": tops[:3],
			}

		def validator_fn(leader_result: gl.vm.Result) -> bool:
			if not isinstance(leader_result, gl.vm.Return):
				leader_fn()
				return False
			mine = leader_fn()
			theirs = leader_result.calldata
			return str(mine.get("level")) == str(theirs.get("level"))

		out = gl.vm.run_nondet(leader_fn, validator_fn)
		self.report = json.dumps({"level_agreed": True, "leader": out})

	@gl.public.write
	def probe_onecall_strict(self, username: str, skill: str) -> None:
		"""One call, with LEVEL + repo_count + total_bytes all on the axis.

		If the level alone commits but this does not, the counts drift and the
		contract may not store them as measured. If both commit, the record can
		carry the evidence and not just the verdict — which is the difference
		between a verification you can audit and one you have to trust."""
		user = str(username)
		lang = str(skill)

		def leader_fn() -> dict:
			st, body = _fetch("https://api.github.com/users/" + user + "/repos?per_page=100&sort=updated")
			if st != 200:
				return {"ok": False, "level": "ERROR", "repo_count": 0, "total_bytes": 0}
			repos = _repo_names(body, 100)
			hits = 0
			total = 0
			for r in repos:
				if r["lang"].lower() != lang.lower():
					continue
				hits += 1
				total += int(r["size"]) * 1024
			return {"ok": True, "level": _level(hits, total), "repo_count": hits, "total_bytes": total}

		def validator_fn(leader_result: gl.vm.Result) -> bool:
			if not isinstance(leader_result, gl.vm.Return):
				leader_fn()
				return False
			mine = leader_fn()
			theirs = leader_result.calldata
			return json.dumps(mine, sort_keys=True) == json.dumps(theirs, sort_keys=True)

		out = gl.vm.run_nondet(leader_fn, validator_fn)
		self.report = json.dumps({"strict_agreed": True, "leader": out})

	@gl.public.write
	def probe_rate_all(self, url: str) -> None:
		"""EVERY bucket /rate_limit reports, not just `core`.

		Round 2 read `resources.core` and found it drained. But GitHub meters
		SEARCH separately — a different resource with its own limit and its own
		reset. If `search` is 10/minute (600/hour) while `core` is 60/hour, then
		a design that asks its question through the search index costs an order
		of magnitude less quota than one that walks repos, and that is the whole
		ballgame."""
		target = str(url)

		def leader_fn() -> dict:
			st, body = _fetch(target)
			try:
				doc = json.loads(body)
			except ValueError:
				return {"status": st, "err": body[:240]}
			out = {"status": st}
			res = doc.get("resources") if isinstance(doc, dict) else None
			if isinstance(res, dict):
				for k in sorted(res.keys()):
					v = res[k]
					if isinstance(v, dict):
						out[str(k)] = str(v.get("remaining")) + "/" + str(v.get("limit")) + " reset=" + str(v.get("reset"))
			return out

		def validator_fn(leader_result: gl.vm.Result) -> bool:
			return isinstance(leader_result, gl.vm.Return)

		self.report = json.dumps(gl.vm.run_nondet(leader_fn, validator_fn))

	@gl.public.write
	def probe_search(self, username: str, skill: str, include_forks: bool) -> None:
		"""THE CANDIDATE THAT COSTS ONE CALL FROM A DIFFERENT BUCKET.

		`search/repositories?q=user:U+language:L` answers "how many of U's repos
		have L as their primary language" in a single request, returns
		`total_count` directly, and carries each matching repo's `size` — which
		is every field the ladder needs.

		Two things are being measured, not one. First: does it work at all from
		validator egress while the core bucket is empty. Second, and the reason
		`include_forks` is a parameter rather than a constant: GitHub search
		EXCLUDES forks by default. A user with forty forked C repos would score
		EXPERT in C under a repo walk without having written a line of it, and
		the fork question decides whether the contract has that hole. Measuring
		both is how the default gets chosen rather than assumed."""
		user = str(username)
		lang = str(skill)
		q = "user:" + user + "+language:" + lang
		if bool(include_forks):
			q = q + "+fork:true"
		url = "https://api.github.com/search/repositories?q=" + q + "&per_page=100&sort=updated"

		def leader_fn() -> dict:
			st, body = _fetch(url)
			if st != 200:
				return {"ok": False, "status": st, "level": "ERROR", "head": body[:240]}
			try:
				doc = json.loads(body)
			except ValueError:
				return {"ok": False, "status": st, "level": "ERROR", "head": body[:240]}
			if not isinstance(doc, dict):
				return {"ok": False, "status": st, "level": "ERROR"}
			items = doc.get("items")
			if not isinstance(items, list):
				items = []
			hits = 0
			total = 0
			forks = 0
			tops = []
			for it in items:
				if not isinstance(it, dict):
					continue
				hits += 1
				if bool(it.get("fork", False)):
					forks += 1
				sz = it.get("size", 0)
				if isinstance(sz, bool) or not isinstance(sz, int):
					sz = 0
				total += int(sz) * 1024
				tops.append({"repo": str(it.get("name", "")), "bytes": int(sz) * 1024, "fork": bool(it.get("fork", False)), "lang": str(it.get("language"))})
			tops.sort(key=lambda x: (-x["bytes"], x["repo"]))
			return {
				"ok": True,
				"status": st,
				"level": _level(hits, total),
				"total_count": int(doc.get("total_count", 0) or 0),
				"returned": hits,
				"forks": forks,
				"total_bytes": total,
				"incomplete": bool(doc.get("incomplete_results", False)),
				"top": tops[:4],
			}

		def validator_fn(leader_result: gl.vm.Result) -> bool:
			if not isinstance(leader_result, gl.vm.Return):
				leader_fn()
				return False
			mine = leader_fn()
			theirs = leader_result.calldata
			return str(mine.get("level")) == str(theirs.get("level"))

		out = gl.vm.run_nondet(leader_fn, validator_fn)
		self.report = json.dumps({"level_agreed": True, "q": q, "leader": out})

	@gl.public.write
	def probe_search_strict(self, username: str, skill: str) -> None:
		"""The search ladder with level + count + bytes ALL on the axis.

		A search index is eventually consistent and served from many shards, so
		this is a genuinely open question in a way the repo walk was not: two
		validators can be answered by shards that disagree. If only the level
		commits, the contract may store the level as consensus and must derive
		the counts from the leader's own evidence rather than claim they were
		independently agreed."""
		user = str(username)
		lang = str(skill)
		url = "https://api.github.com/search/repositories?q=user:" + user + "+language:" + lang + "&per_page=100&sort=updated"

		def leader_fn() -> dict:
			st, body = _fetch(url)
			if st != 200:
				return {"ok": False, "level": "ERROR", "count": 0, "bytes": 0}
			try:
				doc = json.loads(body)
			except ValueError:
				return {"ok": False, "level": "ERROR", "count": 0, "bytes": 0}
			items = doc.get("items") if isinstance(doc, dict) else []
			if not isinstance(items, list):
				items = []
			hits = 0
			total = 0
			for it in items:
				if not isinstance(it, dict):
					continue
				hits += 1
				sz = it.get("size", 0)
				if isinstance(sz, bool) or not isinstance(sz, int):
					sz = 0
				total += int(sz) * 1024
			return {"ok": True, "level": _level(hits, total), "count": hits, "bytes": total}

		def validator_fn(leader_result: gl.vm.Result) -> bool:
			if not isinstance(leader_result, gl.vm.Return):
				leader_fn()
				return False
			mine = leader_fn()
			theirs = leader_result.calldata
			return json.dumps(mine, sort_keys=True) == json.dumps(theirs, sort_keys=True)

		out = gl.vm.run_nondet(leader_fn, validator_fn)
		self.report = json.dumps({"strict_agreed": True, "leader": out})

	@gl.public.write
	def probe_raw_search(self, url: str) -> None:
		"""A search URL passed through VERBATIM, reporting what came back.

		`probe_search` builds its own query, which is exactly what makes it
		useless for the encoding question. `+` is a SPACE in a query string, so
		`language:C++` may reach GitHub as `language:C` followed by two spaces —
		and `#` starts a fragment, so `language:C#` may never leave the client
		at all. C++ and C# are two of the most claimed skills there are; if the
		obvious spelling silently scores them as C, the contract certifies the
		wrong language and every test written against `Python` passes anyway.

		Reports `total_count` and the DISTINCT `language` values of the returned
		items, which is what says whether the filter bound to the right one."""
		target = str(url)

		def leader_fn() -> dict:
			st, body = _fetch(target)
			if st != 200:
				return {"status": st, "head": body[:200]}
			try:
				doc = json.loads(body)
			except ValueError:
				return {"status": st, "err": "unparseable", "head": body[:200]}
			items = doc.get("items") if isinstance(doc, dict) else []
			if not isinstance(items, list):
				items = []
			langs = {}
			for it in items:
				if isinstance(it, dict):
					k = str(it.get("language"))
					langs[k] = int(langs.get(k, 0)) + 1
			return {
				"status": st,
				"total_count": int(doc.get("total_count", 0) or 0),
				"returned": len(items),
				"languages": langs,
			}

		def validator_fn(leader_result: gl.vm.Result) -> bool:
			return isinstance(leader_result, gl.vm.Return)

		self.report = json.dumps(gl.vm.run_nondet(leader_fn, validator_fn))

	@gl.public.view
	def get_report(self) -> str:
		return str(self.report)

	@gl.public.view
	def get_slice(self, start: int, count: int) -> str:
		s = str(self.report)
		a = int(start)
		n = int(count)
		if a < 0:
			a = 0
		if n <= 0 or n > 6000:
			n = 6000
		return s[a:a + n]

	@gl.public.view
	def get_len(self) -> int:
		return int(self.text_len)

	@gl.public.view
	def get_window(self) -> str:
		return str(self.text)
