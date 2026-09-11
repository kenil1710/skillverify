# SkillVerify — design notes and hazards

Referenced from the header of `SkillVerify.py`. Everything here is either a
hazard that cost real debugging or a decision whose reasoning is not recoverable
from the code.

Every claim was **measured on Studionet**, not inferred from documentation.
Where a measurement is the whole argument, the numbers are given.
Probe evidence: [`docs/PROBE.md`](../docs/PROBE.md).

---

## 1. The design in the plan could not have worked, and the probe is why

The plan said: fetch `/users/{U}/repos`, then `/repos/{owner}/{name}/languages`
for each repository, and count bytes of the claimed language. That is the
accurate way to do it and it is what a reader would expect.

It ran. `torvalds/C` scored **EXPERT** from 11 HTTP calls on the first
transaction. Then **every single call after it returned 403.**

`/rate_limit` — which is exempt from the limit it reports — said:

```
limit=60   used=60   reset in 3301s
{"message":"API rate limit exceeded for 44.198.152.104. …"}
```

**One IP. All validators.** And `remaining` was put on the consensus axis and
the transaction **committed**, which is only possible if every node sees the
same bucket. So a verification's real cost is `calls × validators`: the planned
walk over a ten-repository user costs 11 calls on the leader and 11 on every
validator, roughly 55 in a five-node round. **The 60/hour bucket funds one
verification per hour for the entire network.**

It does not degrade gracefully either. The 61st request is a 403, and a naive
reading scores that as `NONE` — so the design fails in the direction of
**silently certifying a real expert as having no skill.**

### What replaced it

`search/repositories?q=user:{U} language:"{L}"` — **one request**, from a
**different bucket**. Measured while `core` was drained:

| resource | remaining/limit |
|---|---|
| `core` | **0/60** |
| `search` | **10/10** |

`search` is metered per **minute**, not per hour: 600/hour against core's 60,
and an exhausted bucket costs a caller a minute rather than an hour. The search
response carries `total_count` *and* each repository's `language` and `size`,
which is every field the ladder needs.

The two paths independently score `torvalds/C` as EXPERT. That agreement across
different data sources is what made the substitution safe rather than merely
cheaper.

---

## 2. THE BUG THAT WOULD HAVE SHIPPED

`q=user:torvalds+language:Notalanguage` returns **200 with 9 repositories.**

**GitHub silently ignores a `language:` qualifier it does not recognise** and
returns the user's repository list unfiltered. Trusting `total_count` therefore
certifies **anybody as EXPERT in any string that is not a real language.**
`verify_skill("torvalds", "Blockchain")` → EXPERT. Nothing about the transaction
looks wrong. No error, no warning, a clean 200 and a plausible number.

The fix is in `_score`: **every returned item is re-checked against its own
`language` field**, and `total_count` is never scored. An unrecognised qualifier
yields zero matches and `NONE`.

The discrepancy stays visible rather than being swallowed — the record stores
GitHub's number as `index_count` beside the count that was earned. Live on
Studionet:

```
 8 RESOLVED  NONE   repos=0  index=9  torvalds / notalanguage
```

GitHub said nine. The contract scored zero. That row is the whole defence.

---

## 3. `+` is a space and `#` is a fragment, and GitHub answers 200 anyway

The same failure by a second route, and it hits **the two most-claimed skills
there are.** Measured:

| query as written | returns | tagged |
|---|---|---|
| `user:nlohmann+language:C++` | 1 repo | **`C`** |
| `user:nlohmann%20language:%22C%2B%2B%22` | 8 repos | `C++` |
| `user:microsoft%20language:C#` | 164 repos | **`C`** |
| `user:microsoft%20language:C%23` | 1087 repos | `C#` |

A `+` in a query string **is** a space, so `language:C++` reaches GitHub as
`language:C` followed by two spaces. A `#` starts a fragment. Neither produces
an error; both produce a confident answer to a different question — *the wrong
language, at a plausible-looking level*.

`_pct` percent-encodes everything outside RFC 3986's unreserved set, and
`_search_url` **always quotes** the language value. Quoting is required for a
multi-word language (`language:"Jupyter Notebook"` finds 31 repositories,
unquoted finds 7, because the second word becomes a free-text term) and
measured to be harmless for a single word (`language:"C"` and `language:C` both
return the same 8). One code path, no branch to get wrong.

**The item re-check from §2 is the second line of defence here.** Even if the
URL builder were wrong, `language:C++` returns items tagged `C`, which do not
match the claim, which scores `NONE`. Two independent defences, and both are
tested against the captured bodies.

---

## 4. A payable method may never raise

`gl.vm.UserError` rolls back contract **storage**. It does **not** return the
value that rode in with the call. The GEN stays in the contract, unaccounted
for. The value transfer settles at the consensus layer independently of GenVM
execution, so a rollback has nothing to undo it with. This is the opposite of
the EVM, where the transfer is part of the same atomic call frame.

`verify_skill` is payable **today**, while the fee is 0, precisely so it does
not have to become payable later — the rule applies from the first line rather
than from the first fee change. Every refusal refunds and returns:

```python
def _reject(self, sender, value, reason) -> str:
    if value > 0:
        self._pay(sender, value)
        self.total_refunded = u128(_clamp(int(self.total_refunded) + value, 0, (1 << 128) - 1))
    return json.dumps({"ok": False, "reason": reason, "refunded": str(value)})
```

The ordering is absolute: **raising after the transfer does not help** — the
revert rolls the refund back too. A rejection has to be a **successful
transaction that happens to refund**.

The counter is **clamped, not added blindly**, because a `u128` write that
overflows RAISES rather than truncating, and a raise on that line would roll
back the refund this method exists to make. The statistic is expendable; the
money is not.

**Every caller must read the return value.** A transaction that succeeded may
still have been turned down. `test_logic.py` fuzzes both payable methods with
every hostile input shape and asserts no exception escapes and every rejection
refunds in full; the live suite asserts the balance actually came back.

### 4a. The same bug, one contract removed

`SkillConsumer.claim_bounty` reads the oracle across a contract boundary. **A
cross-contract view that raises propagates and reverts the caller** — keeping
the bounty. An earlier project shipped exactly that and confiscated a premium
the first time somebody asked about a market that did not exist.

So `_level_of` wraps every oracle call in `try/except` and degrades an
unreachable oracle to "no verification". `test_logic.py` wires a **real**
SkillVerify into the consumer and then makes it raise on demand, because a fake
would return whatever the test author expected and the bug is precisely that the
real one might not.

The oracle helps from its side too: `get_verification` and `get_latest` answer
`found: false` rather than raising. **A view that raises is a liability to every
contract that composes with it.**

---

## 5. The consensus axis is the level *and* the counts it was computed from

`verify_skill`'s validator compares `_compare_key`: the level — `EXPERT`,
`PROFICIENT`, `BEGINNER`, `NONE`, `NO_SUCH_USER`, `UNAVAILABLE` — and, for the
four that are real levels, the `repo_count` and `total_bytes` behind it.

`UNAVAILABLE` is on the axis precisely *because* it is not a level. Validators
must **agree** that the source was unreachable, or one node's rate limit
silently becomes everybody's verdict. It and `NO_SUCH_USER` carry no counts —
a 403 and a 422 have never held a number — so they compare as the bare axis.

### This was narrower, and being narrower was a forgery hole

The axis used to be the level alone. That was a deliberate choice, made for a
measured reason, and it was **wrong** — it is the bug this project was rejected
for, and the reasoning that produced it is left here rather than quietly
deleted, because the mistake is more instructive than the fix.

The stored level was never the leader's level. `_apply` recomputed it from the
leader's `repo_count` and `total_bytes`:

```python
level = _level_for(repo_count, total_bytes)      # from the leader's payload
```

Nothing compared those two numbers. So a leader could report `NONE` — which
every validator looking at a genuinely empty result set would unanimously
agree with — and attach `repo_count=100, total_bytes=10**9` to the same
payload. Consensus passed on `NONE`. The contract then computed `EXPERT` from
the forged counts and stored it, with a content hash over it, as a quorum
result. **A verification the validators voted NONE on lands EXPERT.** It
inverts in both directions: forging zeroes under a real `EXPERT` silently
denies a genuine expert.

Recomputing looked like the safe move — deriving a verdict rather than trusting
one — and it is the exact opposite when the inputs to the derivation are
themselves untrusted. *Recomputing from unagreed evidence is not verification;
it is laundering.*

### What it costs, measured

The probe measured `level` + `repo_count` + `total_bytes` all on the axis and
it **committed**, twice — the counts do agree in practice. But they are not
guaranteed to. Two `nlohmann/c++` verifications, minutes apart:

```
 9 RESOLVED EXPERT repos=8 bytes=489067520 hash=58674b2ea0d6ea70
17 RESOLVED EXPERT repos=8 bytes=489068544 hash=73d1f59a6dff4abd
```

Somebody pushed. The byte count moved by 1,024. A round straddling that push
now lands **UNDETERMINED** where it used to commit, and that is the price.

It is worth paying, and the arithmetic is not close. An `UNDETERMINED` round
writes **nothing** — no record, no counter, no cooldown stamp — so it is a
retry that costs the caller nothing but a resubmission. A forged `EXPERT` is a
`RESOLVED` record, and a `RESOLVED` record is **frozen forever** (rule 5); no
method, owner included, can correct it. A recoverable inconvenience against a
permanent, unfixable lie is not a trade-off, it is an answer.

`test_byte_differences_are_a_disagreement_now_that_the_counts_are_bound`
asserts the cost so it stays a decision rather than becoming a surprise.

### The second gate, and why one is not enough

Consensus is the first line. `_apply` is the second: it re-runs the ladder over
the agreed counts and requires the result to equal the agreed level.

```python
recomputed = _level_for(repo_count, total_bytes)
if recomputed != level:        # incoherent — not scored at all
```

The level is now **checked against** the counts rather than derived from them,
and what is stored is what the validators agreed on: their level, their
`repo_count`, their `total_bytes`.

The two gates catch different things. Consensus catches a leader whose payload
disagrees with what the validators measured. Coherence catches a payload that
is internally contradictory — an `EXPERT` with zero repositories — which
consensus could only catch if some validator happened to disagree with it.
Neither subsumes the other, so `tools/audit_selftest.py` breaks them one at a
time and asserts the audit catches each alone; breaking both together could not
distinguish two working gates from one working gate carrying a dead one.

An incoherent payload is **not** a raise — this path is reachable from a
payable method (rule 1) — and not a score either. The record stays `PENDING`
and `resolve_pending` settles it under the next leader.

### The status classification, and rule 4

| status | meaning | result |
|---|---|---|
| 200 | the index answered | a level |
| 422 | no such user, or unsearchable | `NO_SUCH_USER` → RESOLVED at NONE, `user_found: false` |
| 403 / 429 | the shared bucket is full | `UNAVAILABLE` → **PENDING** |
| 5xx, 0, non-JSON 200 | GitHub is having a moment | `UNAVAILABLE` → **PENDING** |
| other 4xx | something we sent was wrong | `UNAVAILABLE`, never a score |

**422 and 403 must never be conflated.** 422 is permanent and every validator
sees it identically; 403 clears in a minute. Reading the second as the first
would permanently record a working developer as unverified.

### Other consensus rules

- **Never capture `self` in a nondet closure.** It pickles storage and kills the
  leader at `run_time 0s`. Every helper is module level and every value a
  closure needs is copied through `str()`/`int()` first. This is also what lets
  `test_logic.py` exercise the whole pure surface offline in milliseconds — and
  an AST scan proves no closure references `self`.
- **A leader error is RE-RUN, never voted `False`.** Answering `False` turns a
  transient failure into a genuine disagreement and burns a round.
- **The validator re-runs the whole evaluation** — its own request, its own
  parse, its own scoring. A validator that only inspects the leader's payload
  for well-formedness has verified nothing.
- **Hash by hand.** `_fnv` is FNV-1a written out because Python's `hash()` is
  seeded per process. Masked to 64 bits at every step so nothing meets a sized
  integer mid-computation. Fields are joined with `\x1f`, which cannot occur in
  a validated username or skill, so moving a character across a boundary cannot
  forge a collision.

---

## 6. `total_bytes` is repository size, and the record says so

`torvalds/linux` reports `size: 6360776` KB → **6,513,035,264 bytes**. The
repo-walk measured **1,451,702,328** bytes of actual C. These are different
quantities, and the endpoint that produces the second one costs one request per
repository — the budget §1 ruled out.

So the field is stored as the **summed on-disk size of the matching
repositories**, and **every record carries `bytes_basis: "github_repo_size_kb"`**,
as does `get_config`. Labelling it beats overstating by 4× in silence.

The ladder's thresholds (1000 / 500 bytes) work as intended under this basis:
they are a floor that excludes empty and placeholder repositories, which is the
only job they were ever doing. Five empty repositories fail the EXPERT byte
floor, then the PROFICIENT floor, and land at BEGINNER — which is why
`_level_for` falls through rather than branching on repo count alone.

---

## 7. Forks are excluded, by using the default rather than filtering

GitHub search excludes forks unless `fork:true` is passed. `torvalds` is 8
matching C repositories without it and 10 with.

This closes a hole rather than opening one: a user who forks forty C
repositories would otherwise score EXPERT in C without having written a line.
`_search_url` does not pass `fork:true`, and a test asserts the string `fork`
never appears in a built URL.

---

## 8. TreeMap answers ZERO for a missing key, not None

On chain a `TreeMap` with a **scalar** value type answers a missing key with
that type's **zero**. `if m.get(k) is not None` is therefore **true for every
key that was never written**. An earlier project shipped that and every user's
first action was refused as a duplicate.

Struct-valued maps *do* answer `None`, which is why `if found is None` is the
correct idiom for `self.verifications.get(...)` and only for that.

SkillVerify has six scalar-valued maps, and each one is read defensively:

| map | absence encoded as | read through |
|---|---|---|
| `inflight: TreeMap[str, u32]` | `0` (slots hold `id + 1`) | `_as_int(...) - 1` → `-1` |
| `latest_resolved: TreeMap[str, u32]` | `0` (ids start at **1**) | `_as_int(...) <= 0` |
| `last_request_at: TreeMap[str, u64]` | `0` | `last > 0` guard |
| `by_user` / `by_skill` / `by_pair` | **empty array**, not None | `_count_of`, `len(bucket) == 0` |

`_release` writes the `0` sentinel rather than deleting the key, so the absent
case and the released case are literally the same value and there is nothing for
the two semantics to disagree about. **`next_id` starts at 1** specifically so
`0` can mean "none" everywhere.

`test_logic.py`'s stub reproduces the zero-for-missing behaviour rather than
answering `None`, because a stub that answered `None` could never catch this
class of bug.

---

## 9. Two storage APIs this project deliberately does not use

- **`DynArray.pop()`** — `top_repos` is a JSON string field, not a
  `DynArray[str]`. Storing three short names does not justify a storage
  collection whose element-removal API has never been exercised on chain here.
- **`len()` over a TreeMap** — `distinct_users`, `distinct_skills` and
  `distinct_pairs` are maintained as verifications land. `_index` returns
  whether it created the bucket, measured with `len(bucket) == 0` rather than
  `is None` (see §8). O(1), and no reliance on an unmeasured API.

---

## 10. Terminal records are frozen, and it is proved by parsing

A `RESOLVED` or `STALLED` verification can never change. `_mutable` is the one
gate, and it is a named method rather than an inline comparison repeated in
three places because **an inline check can be forgotten in the fourth.**

`tools/ast_audit.py` and `test_logic.py` both parse the file and assert:

- every method that writes a record field passes through `_mutable`;
- the two exempt creators (`verify_skill`, `post_bounty`) allocate a fresh id
  from `next_id` first, so the handle they write through is always brand new;
- **no owner method touches a verification table at all** — not
  `verifications`, not `latest_resolved`, not `inflight`.

`tools/audit_selftest.py` injects each bug class into a copy of the contracts
and asserts the audit reports it, then reverts and asserts it goes clean. **An
audit that cannot fail is decoration**, and a green run from one is worse than
no run because it buys false confidence.

---

## 11. PENDING exists so a full bucket is never an answer

`verify_skill` has two successful outcomes:

- **RESOLVED** — the index answered and the validators agreed on a level.
- **PENDING** — the shared bucket was full. The request is **durably recorded**
  and `resolve_pending` retries it for free.

`settle_stalled` is the backstop. Without it a pair whose verification met a
permanently broken GitHub would hold its in-flight slot forever and **nobody
could ever verify that username and skill again** — the anti-duplicate guard
would have become a denial of service.

Both are **permissionless** and both **run during a pause**. A record belongs to
whoever needs it resolved, not to whoever submitted it; and an owner who could
pause and thereby strand an in-flight record would hold exactly the power the
pause is meant not to include. The window used is the one **frozen on the
record** at request time, so an owner who lengthens the default afterwards
cannot reach backwards and keep an old record in flight.

A stalled record carries **no content hash**. The hash certifies a measured
result and there was never a measurement; emitting one over an empty level would
give an unverified record a verified record's shape.

---

## 12. Smaller things that cost time

- **The runner JSON is the leading `#` block.** Nothing may sit between line 1
  and the `import`. A comment there makes the contract undeployable and the only
  error reported is `invalid_contract`.
- **`_as_text(None)` returns `""`, not `"None"`.** `str(None)` lowercases to
  `none`, which is a perfectly legal GitHub username — so a missing argument
  would have stopped being an error and started being a lookup of somebody
  else's account. The same slip in `_score` would make a repository GitHub could
  not classify match a claim of the skill `"none"`. Both are silent wrong
  answers rather than failures. Caught by the offline suite, not by review.
- **`isinstance(True, int)` is `True` in Python.** A JSON `true` in a repo's
  `size` would otherwise become 1 KB. `_as_int` refuses bools before the int
  branch and `_score` guards the size field explicitly.
- **A typo in `min_level` must DENY, not admit.** `_rank` returns `-1` for
  anything that is not a level, never `0` — because `NONE` is a real level and
  "not a level at all" silently meaning `NONE` would make `is_verified(u, s,
  "expert")` return **true** for everybody. Tested for every casing.
- **The 100-item scan cap never changes a level.** The ladder saturates at 5
  repositories, so a user with 300 and a user with 100 are both EXPERT. Visible
  on chain: `microsoft/c#` stores `repos=100 index=1087`.
- **Reverts hide their reason.** `stderr` and `stdout` are both empty on a
  revert; the message is `receipt.result.payload`. A suite asserting on stderr
  can only check *that* something reverted, never that it reverted for the right
  reason, so every wrong-reason revert passes silently.
- **Studionet and Bradbury report failure in different places.** Studionet
  leaves `txExecutionResultName` undefined and puts the outcome in
  `consensus_data.leader_receipt[0].execution_result`; Bradbury carries no
  `consensus_data`. Reading only one gives `undefined !== "FINISHED_WITH_ERROR"`
  and reports success for a transaction that rolled back. See `outcomeOf` in
  `test/harness.mjs`. They also disagree on where a deploy's address lives.
- **The live suite must be re-runnable.** Wallets are reused between runs, so a
  second run inside 300 seconds meets the contract's own cooldown and every
  downstream assertion would skip — for a reason that is the contract working
  correctly. `verify()` waits the cooldown out rather than reporting a hollow
  pass, and every verification uses its own wallet so only TEST 10 measures the
  cooldown.
- **The mangle is verified, not trusted.** An earlier project's first working
  mangle renamed a parameter onto a name a local already held; every market was
  validated with its own question as its aggregator. It parsed, linted,
  validated, and would have deployed. `test_logic.py` re-runs its whole battery
  against `build/SkillVerify.min.py` through the name map, and asserts no
  replacement collides with an existing name and that the mapping is injective.
