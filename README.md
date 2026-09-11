# SkillVerify — a developer skill verification oracle

**GenLayer Intelligent Contract.** Ask it *"does GitHub user U actually write
language L, and how much?"* Every validator answers independently by querying
GitHub's search index, and what lands on chain is a level — **EXPERT**,
**PROFICIENT**, **BEGINNER** or **NONE** — that a quorum computed separately and
agreed on, plus the evidence they computed it from.

Any other contract can then gate on it:

```python
# in your contract  (v0.6; on the v0.3 runner this is gl.get_contract_at)
oracle = gl.contract.get_at(Address(SKILLVERIFY))
if not oracle.view().is_verified("gvanrossum", "Python", "PROFICIENT"):
    return {"ok": False, "reason": "not qualified"}
```

`contracts/SkillConsumer.py` is a worked example: a bounty that can only be
claimed by a developer the oracle has verified.

## Live

**Studio Dev (chain 61997) — the current deployment, and the only one carrying
the consensus fix.**

| | address | |
|---|---|---|
| **SkillVerify** | `0x4a5db424A4bF1b839081aFFD6a4a2cC3a8C4614f` | [explorer](https://explorer-studio-dev.genlayer.com/address/0x4a5db424A4bF1b839081aFFD6a4a2cC3a8C4614f) |
| **SkillConsumer** | `0x1b4E4f334b02f6D6E60e526503f8E35307c73844` | [explorer](https://explorer-studio-dev.genlayer.com/address/0x1b4E4f334b02f6D6E60e526503f8E35307c73844) |

Owner `0x47E433241944d9c0994D8BEf9Cae539Bb9D0e8a7`. **18/18 read-only checks**,
including the one that matters most — that the consumer reads *this* oracle
**across the contract boundary**, rather than the two merely each existing.
That check is not decoration: the first consumer deployed here passed every
local check and still could not reach the oracle (see the migration note below).

These run the **v0.6 runner**, whose API surface differs from the sources in
`contracts/`. `build/v06/*.v06.py` are the exact deployed bytes, produced by
`python3 tools/to_v06.py`; re-running it reproduces both sha256s recorded in
`deployments.json`.

### Earlier networks — superseded, all pre-fix

| | Bradbury (testnet) | Studionet |
|---|---|---|
| **SkillVerify** | `0xA89c18414E586741b91e057213ca3007A6E06cCf` | `0x502852778bfAB94E48918E7A14D28b126D58cc41` |
| **SkillConsumer** | `0x853fB2E9c895Dcb797Fc8D2c68D2F2aDde025f7B` | `0x08CedAECe6BbB6accE3Ed5B6A0708765a2627B77` |
| | 16/16 config checks | 111 live assertions, 0 failed |

Both hold the artifact whose validator compared the level alone. A Bradbury
redeploy was attempted and is **stuck**: three transactions sit unmined at
nonces 251 and 252, and across a 400-block window nothing larger than ~1.3M gas
was included there while these ask for ~18.4M each. Studio Dev is where the
fixed contract actually runs.

```bash
node test/check_deployment.mjs --network=bradbury
```

### The v0.6 migration, and the one that does not fail loudly

Six substitutions are mechanical — `gl.Contract` → `gl.contract.Contract`,
`gl.message_raw` → `gl.message.raw`, `allow_storage` → `gl.storage.allow`,
`TreeMap`/`DynArray` → `gl.storage.*`, plus the new runner header.

The seventh is the one to know about: **`gl.get_contract_at` is gone in v0.6**,
replaced by `gl.contract.get_at`. It does not crash. `SkillConsumer` wraps every
oracle read in `except Exception` so an unreachable oracle *refunds* rather than
reverting — deliberate, and rule 1 — so the stale spelling deploys clean,
reports the right oracle address from `get_terms`, and silently degrades **every
lookup** to `"oracle unreachable"`. The consumer at
`0x7d0749701D340199B601DD51B47C9571c32112fb` is that build; it is superseded and
should not be used. `get_skill_report`'s `reason` field is what exposes it, which
is why the deployment check asserts on that string rather than on `found`.

The behaviour below was measured on Studionet, where the write suite ran:

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

**The compared axis is the level *and* the counts it was computed from.** The
level alone was not enough, and that was this project's rejection: the stored
level is derived from `repo_count` and `total_bytes`, and nothing compared
those two numbers. A leader could report `NONE` — which validators seeing a
genuinely empty result set unanimously agree with — while attaching
`repo_count=100`, and the contract would compute `EXPERT` from the forged
counts and store it as a quorum result. Recomputing from evidence nobody agreed
on is not verification.

So `_compare_key` binds all three, and `_apply` then checks them against each
other a second time: the ladder re-run over the agreed counts must land on the
agreed level, or the payload is incoherent and is not scored at all. What lands
on chain is what the validators agreed on — their level, their counts.

The price is measured and accepted. Two `nlohmann/c++` verifications minutes
apart stored `489067520` and `489068544` bytes — somebody pushed — and a round
straddling that push now lands **UNDETERMINED** where it used to commit. An
undetermined round writes nothing at all, so it is a free retry; a forged
`EXPERT` is a RESOLVED record, and a RESOLVED record is frozen forever.

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
python3 test/test_logic.py       # 369 offline tests, stdlib only, no chain
python3 tools/ast_audit.py       # 22 checks — every bug class, by parsing
python3 tools/audit_selftest.py  # proves the audit can actually fail
bash tools/build.sh              # minify + mangle -> build/*.min.py
node test/deploy.mjs             # deploy + 13 config checks
node test/e2e.mjs                # 111 live assertions on real validators
node test/verify_onchain.mjs     # re-derive every stored record from chain
```

**369 offline tests.** Pure functions, the scoring engine against **verbatim
GitHub bodies** captured 2026-09-07, the stateful contract driven through a
storage stub that reproduces on-chain `TreeMap` semantics, the consumer wired to
a **real** SkillVerify across the call boundary, and the whole battery re-run
against the **mangled artifact**. Seventeen of them are the consensus-forgery
regression: a `LEADER_FORGE` hook tampers with the leader's payload after it is
computed and before anyone sees it — the exact power a real leader has — and
eight of the seventeen fail if either gate is removed.

**The audit is mutation-tested.** `audit_selftest.py` injects each of the nine
bug classes into a copy of the contracts and asserts the audit reports it, then
reverts and asserts it goes clean. The two consensus gates are injected
**separately**: either alone would have stopped the forgery, so breaking both
at once could not tell a working pair from one working gate carrying a dead
one. An audit that cannot fail is decoration, and
a green run from one is worse than none because it buys false confidence.

| scan | rejection it encodes |
|---|---|
| write-then-raise | a counter incremented before a revert |
| frozen-state | a write reachable after a terminal status |
| unsnapshotted terms | a per-record term read from the live config |
| payable revert | a raise reachable from a payable path, or from a helper it calls |
| owner reach | an owner method that can touch a user record or user funds |
| provenance | an axis that does not bind the counts its level is checked against, or a stored field that is not the agreed evidence |
| `str.replace()` | rejected by the runner |
| `self` in a nondet closure | pickles storage, kills the leader at 0s |
| artifact size | the ceiling that decides whether this deploys |

---

## Deploy

```bash
bash tools/build.sh

# Studio Dev (chain 61997) — the v0.6 runner, and where this currently lives.
# The artifacts are converted first; the sources in contracts/ are v0.3.
python3 tools/to_v06.py          # -> build/v06/*.v06.py

node test/deploy.mjs --network=studionet

# Bradbury — the signer becomes the owner of both contracts.
# Password from the environment, never argv: argv is visible to every process
# on the machine via `ps` and lands in shell history. The leading space keeps
# the export out of history too.
 export GENLAYER_KEYSTORE_PASSWORD='…'
node test/deploy.mjs --network=bradbury --keystore=mywallet

# verify a deployment this session did not perform — read-only, no key needed
node test/check_deployment.mjs --network=bradbury
```

The Studio Dev deploy itself is `scratchpad`-side rather than a committed
script, and two of its constraints are worth carrying forward. studio-dev runs
the **fee policy enabled** with no `feeManagerContract`, so the SDK cannot derive
a deposit on its own: `normalizeTransactionFees(undefined)` yields an all-zero
distribution and the consensus contract refuses the zero-fee transaction. Pass an
explicit `estimateFeesDistribution()` as `fees` (0.1 GEN per deploy). And
`sim_fundAccount`'s amount must be a **hex string** — a JS `Number` serialises as
`1e+21` and the node answers `amount must be a positive integer`, after which the
deploy fails for want of a deposit rather than for anything to do with the code.

Artifacts are **22,259** and **11,069** bytes on v0.3, **22,423** and **11,178**
after the v0.6 conversion — well under the 48,000 budget and under the largest
artifact previously confirmed on Bradbury (37,658). The deploy
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
| [`test/test_logic.py`](test/test_logic.py) | 369 offline tests |
| [`tools/ast_audit.py`](tools/ast_audit.py) | the pre-submission audit |
| [`tools/to_v06.py`](tools/to_v06.py) | the v0.3 → v0.6 conversion, and what it refuses to leave behind |

---

## What is not yet proved on Studio Dev or Bradbury

**Studio Dev has 18/18 read-only checks and no writes.** `total_verifications`
is 0 there: every config property, both contracts' ladders, the never-raise
behaviour of `is_verified` / `get_latest` / `get_verification`, and the
cross-boundary read are verified live — but no `verify_skill` has been
submitted, so the consensus fix has **not** been exercised against a real
validator quorum on chain. Its evidence is the 17 offline regression tests,
8 of which fail if either gate is removed.

The Bradbury pair is likewise deployed and config-verified with **no
verification submitted** — and it holds the pre-fix artifact besides. Every
behavioural claim above (levels, refunds, freezing, the bounty flow) was
measured on Studionet.

Running the write suite on Bradbury needs the eleven wallet roles in
`test/.accounts.json` funded with gas:

```bash
node test/accounts.mjs          # prints the addresses to fund
node test/e2e.mjs --network=bradbury
```

Separately, `settle_stalled` and `resolve_pending` have full offline coverage
but never fired on chain — GitHub answered every live request, so no record ever
landed PENDING. Those paths are exercised in tests, not in production.
