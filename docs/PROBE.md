# Render probe findings — Studionet, 2026-09-07

Throwaway contract [`contracts/_render_probe.py`](../contracts/_render_probe.py),
deployed three times:

| round | address | question |
|---|---|---|
| 1 | `0x0aA1ad56D45aBa97a862Ea816832967a9b674AE2` | can a validator reach `api.github.com`, and does the repo-walk ladder survive consensus? |
| 2 | `0xEc7482C58205bd59754258eddC840cE758585992` | round 1 worked once and then 403'd on everything. Why? |
| 3 | `0x9E9bf1e5fb00344588078895Db5e753AAB9b2F6A` | what does the contract read instead? |

Nothing in SkillVerify imports the probe. What survives is this file and the
six design decisions it forced. Raw transcripts:
[`probe_findings.json`](probe_findings.json), [`probe2_findings.json`](probe2_findings.json),
[`probe3_findings.json`](probe3_findings.json).

The probe ran **before a line of contract logic was written**, and it is the
reason SkillVerify does not walk repositories. The design in the plan would have
worked for exactly one verification per hour across the entire network.

---

## 1. Egress — GitHub answers

Round 1, one transaction, plain GET from inside `gl.vm.run_nondet`:

| Target | Status | Body |
|---|---|---|
| `api.github.com/users/torvalds/repos?per_page=5&sort=updated` | **200** | 26,055 bytes |
| `api.github.com/users/torvalds/repos?per_page=100&sort=updated` | **200** | 62,334 bytes |
| `api.github.com/repos/torvalds/linux/languages` | **200** | 363 bytes, `{"C":1451702328,"Assembly":9614300,…}` |
| `api.github.com/repos/octocat/Spoon-Knife/languages` | **200** | 22 bytes, `{"HTML":355,"CSS":256}` |
| `api.github.com/users/this-user-does-not-exist-…/repos` | **404** | `{"message":"Not Found","status":"404"}` |

Both endpoints named in the plan are reachable and keyless. That is the good
news, and it is the last of it.

## 2. THE FINDING THAT KILLED THE PLANNED DESIGN

Round 1 ran the real ladder — fetch the repo list, then one `/languages` call
per repo — for `torvalds/C`. It **committed**, scored **EXPERT** from 11 HTTP
calls, and produced the right answer:

```
level=EXPERT repos=9 bytes=1462580135 scanned=10 calls=11 errors=0
top=[linux 1451702328, libgit2 7731824, libdc-for-dirk 1374766]
```

**Every single call after it returned 403.** `gvanrossum/Python` → ERROR.
`kenil1710/JavaScript` → ERROR. The strict variant → ERROR. The budget probe
could not even fetch a repo list.

Round 2 asked GitHub itself. `/rate_limit` is **exempt from the limit it
reports**, so it answers while the bucket is empty:

```
limit=60   used=60   reset in 3301s
{"message":"API rate limit exceeded for 44.198.152.104. …"}
```

Two facts, and together they are the whole story:

1. **One IP.** `44.198.152.104`. Every validator egresses through a single NAT.
2. **`remaining` was put on the consensus axis and the transaction COMMITTED** —
   every validator reports the *same* remaining, which is only possible if they
   share one bucket.

So a verification's real cost is **calls × validators**, not calls. The planned
1 + N walk over a 10-repo user costs 11 calls on the leader and 11 on every
validator — roughly 55 in a five-node round. **The 60/hour bucket funds ONE
verification per hour for the entire network**, and it does not degrade
gracefully: the 61st request is a 403 that a naive reading scores as `NONE`.

The plan's design is not slow. It is unusable, and it fails in the direction of
**silently certifying a real expert as having no skill**.

## 3. Two escapes, measured

**`ungh.cc` — ruled out on the evidence.** A keyless, cached GitHub mirror that
answers 200 while GitHub's bucket is empty, so it looked like the answer. Its
repo objects do not carry a `language` field:

```
repos: list[12] dict{createdAt,defaultBranch,description,forks,id,name,
                     pushedAt,repo,stars,updatedAt,watchers}
```

No language, no size. It cannot answer the only question SkillVerify asks.
Recorded here so nobody spends an afternoon rediscovering it.
`api.codetabs.com`'s proxy answered **522** (a Cloudflare failure page).

**GitHub's SEARCH index — a different bucket entirely.** Round 2 read only
`resources.core`. Round 3 read all of them, *while core was still drained*:

| resource | remaining/limit |
|---|---|
| `core` | **0/60** |
| `code_search` | 0/60 |
| `search` | **10/10** |
| `graphql` | 0/0 (needs auth) |
| `integration_manifest` | 5000/5000 |

`search` is metered **per minute**, not per hour, and it was untouched and full
while `core` was empty. 10/minute is **600/hour — ten times the core budget** —
and it is replenished on a minute's timescale, so an exhausted bucket costs a
caller a minute rather than an hour.

## 4. One call answers the whole question

```
search/repositories?q=user:{U}+language:{L}&per_page=100&sort=updated
```

returns `total_count` *and* every matching repository with its `language` and
`size`. One request per validator. Measured:

| query | status | level | repos | forks | notes |
|---|---|---|---|---|---|
| `user:torvalds language:C` | 200 | **EXPERT** | 8 | 0 | agrees with the round-1 walk |
| `user:gvanrossum language:Python` | 200 | **EXPERT** | 8 | 0 | |
| `user:kenil1710 language:JavaScript` | 200 | **EXPERT** | 5 | 0 | |
| `user:torvalds language:Haskell` | 200 | **NONE** | 0 | 0 | the negative case |
| `user:this-user-does-not-exist-…` | **422** | — | — | — | `Validation Failed` |

The round-1 walk and the round-3 search independently score `torvalds/C` as
EXPERT. That agreement across two different data paths is what makes the
substitution safe rather than merely cheaper.

**Forks are excluded by default**, and that closes a hole rather than opening
one. Adding `+fork:true` takes torvalds from 8 matching repos to 10. A user who
forks forty C repositories would have scored EXPERT in C under the repo walk
without writing a line of it; the search default counts only repositories the
user actually owns. SkillVerify does **not** pass `fork:true`.

**A missing user is a 422, not a 404**, and it is not the same as a 403. That
distinction is load-bearing: 422 is a permanent, deterministic "no such user"
that every validator sees identically, and 403 is a shared bucket that will be
full again in a minute. Reading the second as the first would record a real
developer as unverified.

## 5. THE BUG THE PROBE FOUND — and it would have shipped

`q=user:torvalds+language:Nonexistentlang` returns **200 with 9 repositories**.

```json
{"level":"EXPERT","total_count":9,"returned":9,
 "top":[{"repo":"linux","lang":"C"},{"repo":"1590A","lang":"OpenSCAD"},…]}
```

**GitHub silently ignores a `language:` qualifier it does not recognise** and
returns the user's repositories unfiltered. Trusting `total_count` therefore
certifies **anybody as EXPERT in any string that is not a real language.**
`verify_skill("torvalds", "Blockchain")` → EXPERT. That is the entire contract
defeated by a typo, and nothing on the transaction looks wrong.

The fix is in `_score`: **every returned item is re-checked against its own
`language` field**, and `total_count` is never used as the score. Items whose
`language` does not equal the claimed skill are discarded, so an unrecognised
qualifier yields zero matches and `NONE`. `total_count` is still stored, as
`index_count`, precisely so the discrepancy is visible on chain.

`test_logic.py` asserts this directly against the recorded payload
(`test_unrecognised_language_scores_none`), because it is the one bug in this
project that is invisible in every other test.

## 6. Drift — and how much the record may claim

The leader fetched and every validator **re-fetched and compared**:

| comparison | outcome |
|---|---|
| repo list, whole body | **COMMITTED** |
| `/languages`, whole body | **COMMITTED** |
| search response, whole body | **COMMITTED** |
| `level` alone, from the search | **COMMITTED** |
| `level` + `repo_count` + `total_bytes` together | **COMMITTED** |

The last row is the useful one. `search_strict` put all three on the axis and
committed for both `torvalds/C` (`count=8 bytes=6532064256`) and
`kenil1710/JavaScript` (`count=5 bytes=13751296`). A search index is eventually
consistent and shard-served, so this was a genuinely open question — it is the
measurement that permits the stored record to carry its **evidence** and not
only its verdict.

**The consensus axis is still the level string alone.** Committing today is not
a guarantee for every user: a repo pushed mid-round changes `size`, and a
verification that lands UNDETERMINED because one validator's shard was a second
stale is a worse outcome than one whose byte count is a second stale. The
counts are recomputed by every validator and stored from the leader's own
agreed payload; the *level* is what they must agree on.

## 7. `size` is the repository, not the language

`torvalds/linux` reports `size: 6360776` KB → **6,513,035,264 bytes**. The
round-1 `/languages` walk measured **1,451,702,328** bytes of actual C. The two
are different quantities and the search API cannot produce the second one
without the per-repo fan-out that §2 ruled out.

SkillVerify therefore stores `total_bytes` as the **summed on-disk size of the
matching repositories**, and says so on the record itself: every verification
carries `bytes_basis: "github_repo_size_kb"`, and `get_config` returns the same
string. The field is a volume signal, not a linguist byte count, and it is
labelled as one rather than quietly overstating by 4x.

The ladder's thresholds (1000 / 500 bytes) work as intended under this basis:
they are a floor that excludes empty and placeholder repositories, which is the
only job they were ever doing.

## 8. Rounds 4 and 5 — the encoding trap, and it hits C++ and C#

`_search_url` interpolates a user-supplied skill into a query string. `+` **is**
a space to a query parser and `#` starts a fragment, so the two most-claimed
skills in existence were the two most likely to be read as something else.
Round 4 measured every spelling; each row is one live search.

| query as it went on the wire | status | total | languages returned |
|---|---|---|---|
| `user:torvalds+language:C++` | 200 | 8 | **`{"C": 8}`** |
| `user:torvalds+language:C%2B%2B` | 200 | 0 | `{}` |
| `user:torvalds%20language:C%2B%2B` | 200 | 0 | `{}` |
| `user:torvalds%20language:C` | 200 | 8 | `{"C": 8}` |
| `user:microsoft%20language:C%23` | 200 | 1087 | `{"C#": 100}` |
| `user:microsoft%20language:C#` | 200 | 164 | **`{"C": 100}`** |
| `user:jakevdp%20language:%22Jupyter%20Notebook%22` | 200 | 31 | `{"Jupyter Notebook": 31}` |
| `user:jakevdp%20language:Jupyter%20Notebook` | 200 | 7 | `{"Jupyter Notebook": 7}` |
| `user:AFNetworking%20language:Objective-C` | 200 | 15 | `{"Objective-C": 15}` |

Two bolded rows, and both are **200 OK with a plausible number**:

**`language:C++` returns eight repositories, every one of them tagged `C`.**
**`language:C#` returns 164, every one tagged `C`** — where the correct answer
for that user is 1,087 C# repositories. GitHub does not complain about either.
It answers the wrong question, confidently.

The torvalds C++ zero rows are *correct*, not a failure: his only C++ repository
is a fork, and search excludes forks. Round 5 re-ran the C++ case against a user
who genuinely owns non-forked C++ repositories, and settled the quoting rule:

| query | status | total | languages |
|---|---|---|---|
| `user:torvalds%20language:%22C%22` | 200 | 8 | `{"C": 8}` — identical to bare `language:C` |
| `user:nlohmann%20language:%22C%2B%2B%22` | 200 | 8 | `{"C++": 8}` |
| `user:nlohmann%20language:C++` | 200 | **1** | **`{"C": 1}`** — the trap, where the right answer is 8 |
| `user:torvalds%20language:%22Notalanguage%22` | 200 | 9 | `{"C": 8, "OpenSCAD": 1}` |
| `user:kenil1710%20language:%22TypeScript%22` | 200 | 6 | `{"TypeScript": 6}` |

Three rules fall out, and all three are frozen into `_search_url`:

1. **Percent-encode the language value.** Everything outside RFC 3986's
   unreserved set, so no byte a caller supplies can be read as query syntax.
2. **Always quote it.** A multi-word value must be quoted — `"Jupyter Notebook"`
   finds 31 repositories, unquoted finds 7 because the second word becomes a
   free-text term — and quoting a single word was measured to change nothing.
   One code path, no branch to get wrong.
3. **Separate qualifiers with `%20`, never `+`.** A literal `+` is the same trap
   by another route.

The fourth row is the round-3 bug again, **surviving correct quoting**:
`language:"Notalanguage"` still returns nine repositories with a 200. Encoding
does not close it and was never going to — only the per-item `language` re-check
in `_score` does. The two defences are independent, which is the point: the
`C++` trap is caught by `_pct` *and*, if that ever regressed, by the item check
finding items tagged `C` that do not match a claim of `C++`.

---

## What this changed, in one list

1. **The repo walk is gone.** One shared IP, 60/hour, and the planned design
   funds one verification an hour for the whole network (§2).
2. **The source is `search/repositories`** — one call, a separate 10/minute
   bucket, and it independently reproduces the walk's answer (§3, §4).
3. **Every result item is re-checked against its own `language` field**, because
   GitHub ignores an unrecognised `language:` qualifier and would otherwise
   certify anyone as EXPERT in anything (§5).
4. **403 is transient and 422 is permanent.** A verification that meets a full
   bucket is recorded **PENDING** and re-resolved later; it is never scored
   `NONE` (§2, §4).
5. **Forks are excluded**, by using the search default rather than by filtering
   after the fact (§4).
6. **`total_bytes` is repository size and is labelled as such** on every record
   (§7).
7. **The language value is percent-encoded and always quoted** — `language:C++`
   and `language:C#` both answer 200 with repositories tagged `C` (§8).

---

## Confirmed live, after the build

Every finding above was re-checked against the deployed contract on Studionet.
`test/verify_onchain.mjs` reads each stored record back and re-derives its level
from the counts the record itself carries:

```
 4 RESOLVED  EXPERT     repos=8    index=8     torvalds / c
 8 RESOLVED  NONE       repos=0    index=9     torvalds / notalanguage
 9 RESOLVED  EXPERT     repos=8    index=8     nlohmann / c++
10 RESOLVED  EXPERT     repos=100  index=1087  microsoft / c#
15 RESOLVED  NONE       repos=0    index=0     torvalds / haskell
19 RESOLVED  BEGINNER   repos=1    index=1     octocat / html
```

Row 8 is §5 closed on a live validator set: GitHub returned nine repositories
with a 200 and the contract scored zero. Rows 9 and 10 are §8 closed — C++
verified as C++ and C# as C#, not as C. Row 10 also shows the 100-item scan cap
against an index count of 1,087, which does not change the level because the
ladder saturates at five.

Two `nlohmann/c++` verifications minutes apart stored `bytes=489067520` and
`bytes=489068544` — somebody pushed between them — and **both scored EXPERT**.
That is §6's argument for keeping the axis to the level alone, observed rather
than predicted.
