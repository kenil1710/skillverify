# SkillVerify — a developer skill verification oracle

**GenLayer Intelligent Contract.** Ask it *"does GitHub user U actually write
language L, and how much?"* Every validator answers independently by querying
GitHub's search index, and what lands on chain is a level — **EXPERT**,
**PROFICIENT**, **BEGINNER** or **NONE** — that a quorum computed separately and
agreed on, plus the evidence they computed it from.

Any other contract can then gate on it:

```python
# in your contract
oracle = gl.get_contract_at(Address(SKILLVERIFY))
if not oracle.view().is_verified("gvanrossum", "Python", "PROFICIENT"):
    return {"ok": False, "reason": "not qualified"}
```

`contracts/SkillConsumer.py` is a worked example: a bounty that can only be
claimed by a developer the oracle has verified.

## Live

| | Studionet |
|---|---|
| **SkillVerify** | [`0x502852778bfAB94E48918E7A14D28b126D58cc41`](https://studio.genlayer.com/contracts/0x502852778bfAB94E48918E7A14D28b126D58cc41) |
| **SkillConsumer** | `0x08CedAECe6BbB6accE3Ed5B6A0708765a2627B77` |

```
 4 RESOLVED  EXPERT     repos=8    index=8     torvalds / c
 2 RESOLVED  EXPERT     repos=8    index=8     gvanrossum / python
 3 RESOLVED  EXPERT     repos=5    index=5     kenil1710 / javascript
 9 RESOLVED  EXPERT     repos=8    index=8     nlohmann / c++
10 RESOLVED  EXPERT     repos=100  index=1087  microsoft / c#
19 RESOLVED  BEGINNER   repos=1    index=1     octocat / html
15 RESOLVED  NONE       repos=0    index=0     torvalds / haskell
 8 RESOLVED  NONE       repos=0    index=9     torvalds / notalanguage   ← §5
```

That last row is the whole project in one line. Read on.

---

## The two bugs that would have shipped

The probe ran **before a line of contract logic was written**
([`docs/PROBE.md`](docs/PROBE.md)). It found three things, and two of them are
silent wrong answers rather than errors — the kind no amount of contract logic
catches, because the transaction looks perfect.

### 1. GitHub certifies anybody as an expert in anything

```
q=user:torvalds+language:Notalanguage   →   200 OK, 9 repositories
```

**GitHub silently ignores a `language:` qualifier it does not recognise** and
returns the user's whole repository list. Trusting `total_count` makes
`verify_skill("torvalds", "Blockchain")` return **EXPERT**. No error, no
warning, a clean 200 and a plausible number.

`_score` re-checks **every returned item against its own `language` field** and
never scores `total_count`. GitHub's number is still stored, as `index_count`,
so the discrepancy is visible on chain — that is the `repos=0 index=9` row above.

### 2. `C++` is verified as `C`, and `C#` is too

```
q=user:nlohmann+language:C++    →  200 OK,     1 repo, tagged C   (right answer: 8, tagged C++)
q=user:microsoft…language:C#    →  200 OK,   164 repos, tagged C   (right answer: 1087, tagged C#)
```

A `+` in a query string **is** a space; a `#` starts a fragment. Neither
produces an error. Both produce a confident answer to a different question — the
wrong language, at a plausible level — and they hit the two most-claimed skills
there are.

`_pct` percent-encodes the value and `_search_url` always quotes it. The item
re-check from §1 is an independent second defence: `language:C++` returns items
tagged `C`, which do not match, which scores `NONE`.

### 3. The design in the plan could not have worked

The plan said: fetch the repo list, then `/languages` for each repository. It
ran, scored `torvalds/C` as EXPERT from 11 calls — and then **every call after
it returned 403.**

```
limit=60  used=60  reset in 3301s
"API rate limit exceeded for 44.198.152.104."
```

**One IP, all validators**, confirmed by putting `remaining` on the consensus
axis and watching it commit. A verification costs `calls × validators`, so the
planned walk funds **one verification per hour for the entire network** — and
fails toward *silently certifying a real expert as unskilled*.

The replacement is `search/repositories`, which answers in **one request** from
a **separate 10-per-minute bucket** that was still full while `core` was
drained. Both paths independently score `torvalds/C` as EXPERT, which is what
made the substitution safe rather than merely cheaper.

---

## How consensus works

Every validator independently issues **one** request:

```
GET api.github.com/search/repositories?per_page=100&sort=updated
    &q=user:{U}%20language:%22{L}%22
```

counts only the items whose own `language` matches the claim, sums their `size`,
and runs the ladder:

| level | requires |
|---|---|
| **EXPERT** | 5+ repositories, 1000+ bytes |
| **PROFICIENT** | 3+ repositories, 500+ bytes |
| **BEGINNER** | 1+ repository |
| **NONE** | none |

**The compared axis is one string** — the level, plus `NO_SUCH_USER` and
`UNAVAILABLE`. The probe measured that the counts happen to agree too, and the
axis was still kept narrow. Two `nlohmann/c++` verifications minutes apart
stored `489067520` and `489068544` bytes — somebody pushed — and **both scored
EXPERT**. Had the counts been on the axis, that round would have failed for a
reason that has nothing to do with the skill.

**A full rate-limit bucket is never an answer.** A 403 stores the record as
**PENDING** and `resolve_pending` retries it for free; scoring it `NONE` would
certify a working developer as unskilled, permanently, on chain. `settle_stalled`
closes a PENDING record that outlives its window, so a broken source can never
make a username permanently unverifiable.

---

## API

**Write**

| method | |
|---|---|
| `verify_skill(github_username, skill)` | payable, **never reverts** — refunds and returns `{"ok": false}` on refusal. Fee 0; rate limit 1 per wallet per 300s |
| `resolve_pending(verification_id)` | retry a PENDING record. Permissionless, runs during a pause |
| `settle_stalled(verification_id)` | close a PENDING record past its window. Permissionless, runs during a pause |

**Read** — none of these ever revert except `require_verified`, which is the
assertion form.

| method | |
|---|---|
| `is_verified(user, skill, min_level) → bool` | the composability primitive. False for anything unmet, unknown or malformed |
| `require_verified(user, skill, min_level)` | reverts unless met |
| `get_verification(id)` | full record; `found: false` for an unknown id |
| `get_latest(user, skill)` | the record the gate reads, plus `fresh` and `pending_id` |
| `get_verifications_by_user(user, offset, limit)` | newest first |
| `get_verifications_by_skill(skill, offset, limit)` | newest first |
| `get_stats()` / `get_config()` | totals; levels, thresholds, `bytes_basis`, source |

**Owner** — `set_fee`, `set_cooldown`, `set_resolve_window`,
`set_freshness_window`, `pause`, `unpause`, `transfer_ownership`,
`withdraw_fees`. **No owner method can touch a verification**, and an AST scan
proves it: none of them so much as names `verifications`, `latest_resolved` or
`inflight`. Pause never blocks reads, `resolve_pending` or `settle_stalled`.

### Stored per verification

`github_username`, `skill`, `level`, `repo_count`, `total_bytes`, `top_repos`,
`content_hash`, `verified_at`, `verified_by` — plus `index_count` (GitHub's own
number, for audit), `bytes_basis`, and the `resolve_window` and `fee_snapshot`
frozen at request time.

`total_bytes` is the **summed on-disk size of the matching repositories**, not a
Linguist byte count — the endpoint producing the latter costs one request per
repository, which §3 ruled out. Every record says so in `bytes_basis`, and so
does `get_config`. Labelling it beats overstating by 4× in silence.

---

## Verification

```bash
python3 test/test_logic.py       # 350 offline tests, stdlib only, no chain
python3 tools/ast_audit.py       # 17 checks — every bug class, by parsing
python3 tools/audit_selftest.py  # proves the audit can actually fail
bash tools/build.sh              # minify + mangle -> build/*.min.py
node test/deploy.mjs             # deploy + 13 config checks
node test/e2e.mjs                # 111 live assertions on real validators
node test/verify_onchain.mjs     # re-derive every stored record from chain
```

**350 offline tests.** Pure functions, the scoring engine against **verbatim
GitHub bodies** captured 2026-09-07, the stateful contract driven through a
storage stub that reproduces on-chain `TreeMap` semantics, the consumer wired to
a **real** SkillVerify across the call boundary, and the whole battery re-run
against the **mangled artifact**.

**The audit is mutation-tested.** `audit_selftest.py` injects each of the seven
bug classes into a copy of the contracts and asserts the audit reports it, then
reverts and asserts it goes clean. An audit that cannot fail is decoration, and
a green run from one is worse than none because it buys false confidence.

| scan | rejection it encodes |
|---|---|
| write-then-raise | a counter incremented before a revert |
| frozen-state | a write reachable after a terminal status |
| unsnapshotted terms | a per-record term read from the live config |
| payable revert | a raise reachable from a payable path, or from a helper it calls |
| owner reach | an owner method that can touch a user record or user funds |
| provenance | a stored field not recomputed from the agreed evidence |
| `str.replace()` | rejected by the runner |
| `self` in a nondet closure | pickles storage, kills the leader at 0s |
| artifact size | the ceiling that decides whether this deploys |

---

## Deploy

```bash
bash tools/build.sh
node test/deploy.mjs --network=studionet

# Bradbury — the signer becomes the owner of both contracts.
# Password from the environment, never argv: argv is visible to every process
# on the machine via `ps` and lands in shell history. The leading space keeps
# the export out of history too.
 export GENLAYER_KEYSTORE_PASSWORD='…'
node test/deploy.mjs --network=bradbury --keystore=mywallet
```

Artifacts are **21,741** and **11,069** bytes — well under the 48,000 budget and
under the largest artifact previously confirmed on Bradbury (37,658). The deploy
script asserts 13 config properties after the fact, including that the consumer
actually reads *this* oracle and that both contracts' level ladders agree — a
mismatch has to surface at deploy time, not at the first claim.

---

## Reading order

| file | |
|---|---|
| [`docs/PROBE.md`](docs/PROBE.md) | what was measured on chain, and what it forced |
| [`contracts/NOTES.md`](contracts/NOTES.md) | every hazard and the reasoning behind each decision |
| [`contracts/SkillVerify.py`](contracts/SkillVerify.py) | the oracle |
| [`contracts/SkillConsumer.py`](contracts/SkillConsumer.py) | the composability example |
| [`test/test_logic.py`](test/test_logic.py) | 350 offline tests |
| [`tools/ast_audit.py`](tools/ast_audit.py) | the pre-submission audit |
