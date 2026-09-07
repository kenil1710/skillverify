/**
 * Live end-to-end suite. Real validators, real GitHub, real consensus.
 *
 *   node e2e.mjs [--network=studionet]
 *
 * WHAT THIS PROVES THAT test_logic.py CANNOT: that independent validators,
 * fetching GitHub seconds apart from a SHARED IP, agree on a level often enough
 * for the contract to work — and that when they cannot, the record lands
 * PENDING instead of being scored wrong.
 *
 * PACING IS PART OF THE TEST, not a workaround. docs/PROBE.md 3: the search
 * bucket is 10 requests per MINUTE and every validator shares one egress IP, so
 * a verification costs (1 x validators) against that bucket. Firing the suite
 * flat out would exhaust it and every later verification would land PENDING —
 * which is correct behaviour but proves nothing. The suite waits instead, and
 * treats a PENDING as a first-class result rather than a failure.
 */
import { readFileSync } from "node:fs";
import { connect, argOf, retry, sleep, returnedJson } from "./harness.mjs";

const networkName = argOf("network", "studionet");
const deployed = JSON.parse(readFileSync(new URL("./.deployed.json", import.meta.url), "utf8"));
const ORACLE = argOf("oracle", deployed.SkillVerify.address);
const CONSUMER = argOf("consumer", deployed.SkillConsumer.address);
const GEN = 10n ** 18n;

// One search request per validator per verification, against a 10/minute
// bucket. 25s between writes keeps the suite inside it with room for the
// validator set to grow.
const PACE_MS = Number(argOf("pace", "25000"));

const owner = connect({ networkName, address: ORACLE, role: "client" });
const alice = connect({ networkName, address: ORACLE, role: "alice" });
const bob = connect({ networkName, address: ORACLE, role: "bob" });
const carol = connect({ networkName, address: ORACLE, role: "carol" });
const outsider = connect({ networkName, address: ORACLE, role: "outsider" });
// EVERY VERIFICATION GETS ITS OWN WALLET. The contract's own rate limit is one
// verification per wallet per 300 seconds, so reusing a signer makes the suite
// measure the cooldown instead of the thing under test — and a rejected call
// reads deceptively like a rate-limited GitHub if the reporting is careless.
const dave = connect({ networkName, address: ORACLE, role: "dave" });
const erin = connect({ networkName, address: ORACLE, role: "erin" });
const frank = connect({ networkName, address: ORACLE, role: "frank" });
const grace = connect({ networkName, address: ORACLE, role: "grace" });
const heidi = connect({ networkName, address: ORACLE, role: "heidi" });

const cAlice = connect({ networkName, address: CONSUMER, role: "alice" });
const cBob = connect({ networkName, address: CONSUMER, role: "bob" });
const cCarol = connect({ networkName, address: CONSUMER, role: "carol" });
const cOutsider = connect({ networkName, address: CONSUMER, role: "outsider" });

let passed = 0, failed = 0, notes = 0;
const failures = [];

function check(label, ok, detail = "") {
  if (ok) { passed++; console.log(`    ok   ${label}`); }
  else { failed++; failures.push(label + (detail ? ` — ${detail}` : "")); console.log(`    FAIL ${label}${detail ? `  (${detail})` : ""}`); }
  return ok;
}
function note(label, detail = "") { notes++; console.log(`    ..   ${label}${detail ? `  (${detail})` : ""}`); }
function head(n, title) { console.log(`\n── TEST ${n}: ${title}`); }

/**
 * Submit a verification and classify the outcome into the FOUR distinct things
 * it can be. Collapsing any two of them is how a suite reports a green run over
 * a broken contract:
 *
 *   resolved  — validators agreed on a level. The only case that asserts.
 *   pending   — they agreed GitHub was unavailable. A correct outcome, and the
 *               whole point of rule 4, but it proves nothing about scoring.
 *   refused   — the CONTRACT turned the call down (rate limit, bad input). A
 *               successful transaction that refunded. NOT a GitHub problem.
 *   unsettled — the round did not reach consensus, or the RPC gave up.
 */
async function verify(who, user, skill, { value = 0n, pace = true, retries = 1 } = {}) {
  if (pace) await sleep(PACE_MS);
  for (let attempt = 0; ; attempt++) {
    const out = await who.send("verify_skill", [user, skill], value);
    const body = returnedJson(out);
    let kind = "unsettled";
    if (out.ok) {
      if (out.returnReadable && body?.ok === false) kind = "refused";
      else if (body?.status === "PENDING") kind = "pending";
      else kind = "resolved";
    }
    const reason = body?.reason ?? out.revertReason ?? out.status;

    // THE SUITE MUST BE RE-RUNNABLE. Wallets are reused between runs, so a
    // second run inside 300 seconds meets the contract's own cooldown and every
    // assertion downstream would be skipped for a reason that is the contract
    // working correctly. Wait it out rather than reporting a hollow pass.
    const cooling = kind === "refused" && /rate limited/.test(String(reason));
    if (cooling && attempt < retries) {
      const left = Number(String(reason).match(/(\d+)s remaining/)?.[1] ?? 300);
      console.log(`         (${who.account.address.slice(0, 10)} is inside its cooldown — waiting ${left + 5}s)`);
      await sleep((left + 5) * 1000);
      continue;
    }
    // A full GitHub bucket is worth one retry too: it refills every minute.
    if (kind === "pending" && attempt < retries) {
      console.log(`         (GitHub was unavailable — waiting 70s for the search bucket)`);
      await sleep(70_000);
      continue;
    }
    return { out, body, kind, reason };
  }
}

/** Report a non-resolved verification honestly, saying WHICH of the three. */
function explain(label, v) {
  if (v.kind === "refused") note(`${label}: the CONTRACT refused the call`, v.reason);
  else if (v.kind === "pending") note(`${label}: landed PENDING — GitHub was unavailable`, v.reason);
  else note(`${label}: the round did not settle`, `${v.out.status} ${v.reason}`.trim());
}

async function latest(user, skill) {
  return owner.viewJson("get_latest", [user, skill]);
}

console.log(`SkillVerify E2E — ${networkName}`);
console.log(`  oracle    ${ORACLE}`);
console.log(`  consumer  ${CONSUMER}`);
console.log(`  pacing    ${PACE_MS}ms between writes (search bucket is 10/minute, shared IP)`);

// ───────────────────────────────────────────────────────── 1. CONFIG
head(1, "the deployed configuration is what the source says");
{
  const cfg = await owner.viewJson("get_config");
  check("four levels, lowest first", JSON.stringify(cfg.levels) === '["NONE","BEGINNER","PROFICIENT","EXPERT"]', JSON.stringify(cfg.levels));
  check("forks are excluded", cfg.forks_counted === false);
  check("bytes basis is declared on chain", cfg.bytes_basis === "github_repo_size_kb", cfg.bytes_basis);
  check("the source is the search index, not the repo walk", String(cfg.source).includes("/search/repositories"), cfg.source);
  check("EXPERT threshold is 5 repos", cfg.thresholds?.EXPERT?.repos === 5);
  const stats = await owner.viewJson("get_stats");
  check("stats read cleanly", typeof stats.total_verifications === "number");
}

// ─────────────────────────────────────────── 2. REAL USERS, REAL LEVELS
head(2, "real GitHub users score the level their code justifies");
const scored = {};
for (const [role, who, user, skill, expected] of [
  ["alice", alice, "torvalds", "C", "EXPERT"],
  ["bob", bob, "gvanrossum", "Python", "EXPERT"],
  ["carol", carol, "kenil1710", "JavaScript", "EXPERT"],
]) {
  const v = await verify(who, user, skill);
  if (v.kind !== "resolved") {
    explain(`${user}/${skill}`, v);
    scored[`${user}/${skill}`] = { pending: true };
    continue;
  }
  const row = await latest(user, skill);
  if (!row.found) {
    note(`${user}/${skill} resolved but is not the latest for the pair`, JSON.stringify(row).slice(0, 100));
    scored[`${user}/${skill}`] = { pending: true };
    continue;
  }
  scored[`${user}/${skill}`] = row;
  check(`${user} is ${expected} in ${skill}`, row.level === expected, `got ${row.level}, ${row.repo_count} repos`);
  check(`${user}/${skill} carries a content hash`, typeof row.content_hash === "string" && row.content_hash.length === 16, row.content_hash);
  check(`${user}/${skill} names its top repos`, Array.isArray(row.top_repos) && row.top_repos.length > 0, JSON.stringify(row.top_repos));
  check(`${user}/${skill} says what its bytes mean`, row.bytes_basis === "github_repo_size_kb");
  console.log(`         ${row.level}  ${row.repo_count} repos  ${row.total_bytes} bytes  top=${JSON.stringify(row.top_repos)}`);
}

// ────────────────────────────────────── 3. THE NEGATIVE CASE MUST BE NONE
head(3, "a skill the user does not have scores NONE, not an error");
{
  const v = await verify(dave, "torvalds", "Haskell");
  if (v.kind === "resolved") {
    check("torvalds is NONE in Haskell", v.body.level === "NONE", v.body.level);
    check("zero repos reported", v.body.repo_count === 0, String(v.body.repo_count));
    check("a NONE record still carries a content hash", String(v.body.content_hash).length === 16, v.body.content_hash);
  } else { explain("torvalds/Haskell", v); }
}

// ──────────────── 4. THE BUG THE PROBE FOUND, ON A LIVE VALIDATOR SET
head(4, "an unrecognised language scores NONE — docs/PROBE.md §5");
{
  // GitHub answers 200 and returns the user's WHOLE repo list for a language
  // qualifier it does not recognise. Trusting total_count would certify
  // torvalds as EXPERT in "Notalanguage". This is the assertion that proves
  // the item-level re-check is live on chain and not just in the unit tests.
  const v = await verify(erin, "torvalds", "Notalanguage");
  if (v.kind === "resolved") {
    check("torvalds is NOT an expert in a language that does not exist", v.body.level === "NONE", v.body.level);
    check("repo_count is zero despite a 200 carrying nine items", v.body.repo_count === 0, String(v.body.repo_count));
    const row = await latest("torvalds", "Notalanguage");
    check("GitHub's inflated total_count is recorded but NOT scored", row.index_count > row.repo_count,
      `index_count=${row.index_count} repo_count=${row.repo_count}`);
  } else { explain("torvalds/Notalanguage", v); }
}

// ──────────────────────────── 5. THE URL-ENCODING TRAP, ON A LIVE SET
head(5, "C++ is verified as C++ and not as C — docs/PROBE.md §4");
{
  const v = await verify(frank, "nlohmann", "C++");
  if (v.kind === "resolved") {
    // The naive spelling returns ONE repo tagged C. The encoded one returns 8
    // tagged C++. A level of EXPERT here is only reachable through _pct.
    check("nlohmann is EXPERT in C++", v.body.level === "EXPERT", `${v.body.level} with ${v.body.repo_count} repos`);
    check("more than the one repo the + trap would have found", v.body.repo_count > 1, String(v.body.repo_count));
  } else { explain("nlohmann/C++", v); }

  // C# through the same path — the other half of the encoding trap.
  const cs = await verify(grace, "microsoft", "C#");
  if (cs.kind === "resolved") {
    check("microsoft is EXPERT in C#", cs.body.level === "EXPERT", `${cs.body.level} with ${cs.body.repo_count} repos`);
    const row = await latest("microsoft", "C#");
    check("and the record says C# rather than C", row.skill === "c#", row.skill);
  } else { explain("microsoft/C#", cs); }
}

// ──────────────────────────────────────── 6. COMPOSABILITY PRIMITIVES
head(6, "is_verified and require_verified agree, and never lie");
{
  const target = Object.entries(scored).find(([, v]) => v && !v.pending && v.level === "EXPERT")
    ?? await anyResolved("EXPERT");
  if (!target) { note("no EXPERT record available to gate on"); }
  else {
    const [key, row] = target;
    const user = row.github_username ?? key.split("/")[0];
    const skill = row.skill ?? key.split("/")[1];
    for (const level of ["NONE", "BEGINNER", "PROFICIENT", "EXPERT"]) {
      const ok = await owner.view("is_verified", [user, skill, level]);
      check(`is_verified(${user}, ${skill}, ${level}) is true`, ok === true, String(ok));
    }
    const typo = await owner.view("is_verified", [user, skill, "expert"]);
    check("a lowercase min_level DENIES rather than admits", typo === false, String(typo));
    const guru = await owner.view("is_verified", [user, skill, "GURU"]);
    check("an invented min_level denies", guru === false, String(guru));
    const unknown = await owner.view("is_verified", ["nobody-at-all-here", "Cobol", "BEGINNER"]);
    check("an unverified pair is false, not an error", unknown === false, String(unknown));

    const req = await owner.viewJson("require_verified", [user, skill, "PROFICIENT"]);
    check("require_verified passes and returns the record", req.ok === true && req.level === "EXPERT", JSON.stringify(req.level));

    let reverted = false;
    try { await owner.view("require_verified", ["nobody-at-all-here", "Cobol", "EXPERT"]); }
    catch { reverted = true; }
    check("require_verified REVERTS for an unverified pair", reverted);
  }
}

// ───────────────────────────────────────── 7. VIEWS NEVER REVERT
head(7, "an unknown id is an absence, never a revert");
{
  // A view that raises reverts every contract that reads it, including payable
  // ones, and takes their callers' value with it. This is the property that
  // makes the oracle safe to compose with.
  for (const id of [0, 999999, 4294967295]) {
    const row = await owner.viewJson("get_verification", [id]);
    check(`get_verification(${id}) returns found:false`, row.found === false, JSON.stringify(row).slice(0, 80));
  }
  const empty = await owner.viewJson("get_verifications_by_user", ["nobody-at-all-here", 0, 10]);
  check("an unknown user lists empty rather than reverting", empty.total === 0 && Array.isArray(empty.verifications));
  const emptySkill = await owner.viewJson("get_verifications_by_skill", ["cobol-fortran-algol", 0, 10]);
  check("an unknown skill lists empty", emptySkill.total === 0);
}

// ──────────────────────────── 8. PAYABLE REJECTIONS REFUND, NEVER REVERT
head(8, "a refused verification REFUNDS — it never keeps the value");
{
  // The ClaimStake/Pavel rejection. GenVM rolls back storage on a UserError but
  // NOT the value that rode in, so a rejection has to be a SUCCESSFUL
  // transaction that happens to refund.
  const before = await outsider.read.getBalance({ address: outsider.account.address });
  const out = await outsider.send("verify_skill", ["", "Python"], GEN);
  const body = returnedJson(out);
  check("the transaction SUCCEEDED", out.ok === true, `${out.status} ${out.revertReason || ""}`.trim());
  if (out.returnReadable) {
    check("but the return says ok:false", body?.ok === false, JSON.stringify(body).slice(0, 120));
    check("and it names the reason", typeof body?.reason === "string" && body.reason.length > 0, body?.reason);
    check("and it reports the refund", String(body?.refunded) === String(GEN), String(body?.refunded));
  } else {
    note("return value unreadable on this network — checking the balance instead");
  }
  // Transfers apply on FINALIZATION, not acceptance, so the balance converges.
  let recovered = false;
  for (let i = 0; i < 30 && !recovered; i++) {
    await sleep(4000);
    const now = await outsider.read.getBalance({ address: outsider.account.address });
    if (now >= before - GEN / 100n) recovered = true;
  }
  check("the 1 GEN came back", recovered);
  const stats = await owner.viewJson("get_stats");
  check("the refund is accounted for", BigInt(stats.total_refunded) >= GEN, stats.total_refunded);
}

head(9, "a refused verification writes NO state");
{
  const before = await owner.viewJson("get_stats");
  const out = await outsider.send("verify_skill", ["bad--name", "Python"], 0n);
  const body = returnedJson(out);
  check("refused", out.ok === true && (!out.returnReadable || body?.ok === false));
  const after = await owner.viewJson("get_stats");
  check("total_verifications did not move", before.total_verifications === after.total_verifications,
    `${before.total_verifications} -> ${after.total_verifications}`);
  check("next_id did not move", before.next_id === after.next_id, `${before.next_id} -> ${after.next_id}`);
  check("users_verified did not move", before.users_verified === after.users_verified);
}

// ───────────────────────────────────────────────── 10. RATE LIMITING
head(10, "one verification per wallet per 300 seconds");
{
  // Two calls BACK TO BACK from one wallet. Asserting on elapsed suite time
  // instead would make this test pass or fail depending on how slow the rest of
  // the run was, which is how a cooldown test comes to measure nothing.
  const first = await verify(heidi, "octocat", "HTML", { retries: 1 });
  if (first.kind === "unsettled") { note("the first call did not settle", first.reason); }
  else {
    check("the first call from a fresh wallet is accepted", first.kind !== "refused", first.reason);
    const second = await heidi.send("verify_skill", ["torvalds", "C"], 0n);
    const body = returnedJson(second);
    check("the transaction still succeeded (a refusal is not a revert)", second.ok === true, second.status);
    if (second.returnReadable) {
      check("the immediate second request from that wallet is refused", body?.ok === false, JSON.stringify(body).slice(0, 100));
      check("and it says how long is left", String(body?.reason || "").includes("rate limited"), body?.reason);
    } else {
      note("return unreadable on this network — cannot assert the reason");
    }
  }
}

// ──────────────────────────────────────── 11. TERMINAL RECORDS ARE FROZEN
/**
 * Any RESOLVED record on chain, from this run or an earlier one.
 *
 * TEST 11 and TEST 13 assert properties of a resolved record — that it is
 * frozen, and that a bounty can be gated on it. Neither needs the record to
 * have been created by THIS run, and tying them to it makes both tests silently
 * skip whenever GitHub's shared bucket happens to be full.
 */
async function anyResolved(minLevel = null) {
  const RANK = { NONE: 0, BEGINNER: 1, PROFICIENT: 2, EXPERT: 3 };
  const stats = await owner.viewJson("get_stats");
  for (let id = Number(stats.next_id) - 1; id >= 1; id--) {
    const row = await owner.viewJson("get_verification", [id]);
    if (!row.found || row.status !== "RESOLVED") continue;
    if (minLevel && RANK[row.level] < RANK[minLevel]) continue;
    return [`${row.github_username}/${row.skill}`, row];
  }
  return null;
}

head(11, "a RESOLVED verification can never change");
{
  const target = Object.entries(scored).find(([, v]) => v && !v.pending) ?? await anyResolved();
  if (!target) { note("no resolved record to freeze-test"); }
  else {
    const id = target[1].verification_id;
    const before = await owner.viewJson("get_verification", [id]);
    const out = await owner.send("resolve_pending", [id], 0n);
    const body = returnedJson(out);
    check("resolve_pending refuses a RESOLVED record", !out.returnReadable || body?.ok === false, JSON.stringify(body).slice(0, 120));
    const stall = await owner.send("settle_stalled", [id], 0n);
    const sbody = returnedJson(stall);
    check("settle_stalled refuses a RESOLVED record", !stall.returnReadable || sbody?.ok === false, JSON.stringify(sbody).slice(0, 120));
    const after = await owner.viewJson("get_verification", [id]);
    check("the level is unchanged", before.level === after.level, `${before.level} -> ${after.level}`);
    check("the content hash is unchanged", before.content_hash === after.content_hash);
    check("the repo count is unchanged", before.repo_count === after.repo_count);
  }
}

// ───────────────────────────────────────────────── 12. OWNER LIMITS
head(12, "the owner can steer the contract but cannot rewrite a verification");
{
  const target = Object.entries(scored).find(([, v]) => v && !v.pending) ?? await anyResolved();
  const id = target ? target[1].verification_id : null;
  const before = id ? await owner.viewJson("get_verification", [id]) : null;

  const notOwner = await outsider.send("set_fee", [String(GEN)], 0n);
  check("a stranger cannot set the fee", notOwner.ok === false, notOwner.status);
  const notOwner2 = await outsider.send("pause", [], 0n);
  check("a stranger cannot pause", notOwner2.ok === false, notOwner2.status);

  const paused = await owner.send("pause", [], 0n);
  check("the owner can pause", paused.ok === true, paused.revertReason || paused.status);
  const cfg = await owner.viewJson("get_config");
  check("the config reports it", cfg.paused === true);

  // Reads keep working under a pause. Pause stops new risk arriving; it must
  // never trap a record or block a consumer.
  if (id) {
    const row = await owner.viewJson("get_verification", [id]);
    check("reads still work while paused", row.found === true);
    const gate = await owner.view("is_verified", [row.github_username, row.skill, "BEGINNER"]);
    check("the gate still answers while paused", typeof gate === "boolean");
  }
  const blocked = await bob.send("verify_skill", ["octocat", "HTML"], 0n);
  const bbody = returnedJson(blocked);
  check("but a new verification is refused while paused", !blocked.returnReadable || bbody?.ok === false, JSON.stringify(bbody).slice(0, 100));

  const un = await owner.send("unpause", [], 0n);
  check("the owner can unpause", un.ok === true);

  if (id && before) {
    const after = await owner.viewJson("get_verification", [id]);
    check("nothing the owner did touched the record", before.level === after.level && before.content_hash === after.content_hash);
  }
  const overFee = await owner.send("set_fee", ["1000000000000000000000"], 0n);
  check("the fee ceiling is enforced", overFee.ok === false, overFee.revertReason?.slice(0, 80));
}

// ─────────────────────────────────────────── 13. THE CONSUMER, LIVE
head(13, "a bounty gated on a real verification");
{
  const target = Object.entries(scored).find(([, v]) => v && !v.pending && v.level === "EXPERT")
    ?? await anyResolved("PROFICIENT");
  if (!target) { note("no sufficiently-skilled verification available — skipping the bounty flow"); }
  else {
    const [key, row] = target;
    const user = row.github_username ?? key.split("/")[0];
    const skill = row.skill ?? key.split("/")[1];
    // Gate at the level the record actually holds, so the flow exercises a real
    // pass rather than depending on which user happened to resolve first.
    const gateLevel = row.level === "EXPERT" ? "PROFICIENT" : row.level;

    const posted = await cBob.send("post_bounty", ["Port the parser", skill, gateLevel], GEN);
    const pbody = returnedJson(posted);
    check("the bounty is funded", posted.ok === true && (!posted.returnReadable || pbody?.ok === true),
      JSON.stringify(pbody).slice(0, 120));
    const bountyId = pbody?.bounty_id ?? 1;

    const report = await cCarol.viewJson("get_skill_report", [user, skill]);
    check("the consumer reads the oracle across the boundary", report.found === true && report.level === row.level,
      JSON.stringify(report).slice(0, 140));
    const gate = await cCarol.view("check_skill", [user, skill, gateLevel]);
    check("check_skill agrees", gate === true, String(gate));

    // The claim: real money moving on the strength of a consensus verification.
    const beforeBal = await cCarol.read.getBalance({ address: cCarol.account.address });
    const claimed = await cCarol.send("claim_bounty", [bountyId, user], 0n);
    const cbody = returnedJson(claimed);
    check("the claim succeeds", claimed.ok === true && (!claimed.returnReadable || cbody?.ok === true),
      JSON.stringify(cbody).slice(0, 160));
    if (cbody?.ok) {
      check("it cites the verification it relied on", cbody.verification_id === row.verification_id,
        `${cbody.verification_id} vs ${row.verification_id}`);
      check("and the content hash matches the oracle's", cbody.content_hash === row.content_hash);
    }
    let paid = false;
    for (let i = 0; i < 30 && !paid; i++) {
      await sleep(4000);
      const now = await cCarol.read.getBalance({ address: cCarol.account.address });
      if (now > beforeBal) paid = true;
    }
    check("the reward actually landed", paid);

    const again = await cCarol.send("claim_bounty", [bountyId, user], 0n);
    const abody = returnedJson(again);
    check("a claimed bounty cannot be claimed twice", !again.returnReadable || abody?.ok === false,
      JSON.stringify(abody).slice(0, 120));

    // An unqualified claimant is refused and nothing moves.
    const posted2 = await cBob.send("post_bounty", ["Second", skill, "EXPERT"], GEN);  // deliberately unmet
    const p2 = returnedJson(posted2);
    const id2 = p2?.bounty_id;
    if (id2) {
      const refused = await cAlice.send("claim_bounty", [id2, "nobody-at-all-here"], 0n);
      const rbody = returnedJson(refused);
      check("an unverified claimant is refused", !refused.returnReadable || rbody?.ok === false,
        JSON.stringify(rbody).slice(0, 120));
      const still = await cBob.viewJson("get_bounty", [id2]);
      check("and the bounty is still OPEN", still.status === "OPEN", still.status);

      // Only the poster can take it back — not the owner, not a stranger.
      const notPoster = await cOutsider.send("withdraw_bounty", [id2], 0n);
      const npbody = returnedJson(notPoster);
      check("a stranger cannot withdraw the bounty", !notPoster.returnReadable || npbody?.ok === false,
        JSON.stringify(npbody).slice(0, 120));
      const back = await cBob.send("withdraw_bounty", [id2], 0n);
      const bbody2 = returnedJson(back);
      check("the poster can", back.ok === true && (!back.returnReadable || bbody2?.ok === true),
        JSON.stringify(bbody2).slice(0, 120));
    }

    const terms = await cBob.viewJson("get_terms");
    check("the consumer's books balance",
      BigInt(terms.total_posted) === BigInt(terms.total_paid) + BigInt(terms.total_withdrawn) + BigInt(terms.open_liability),
      JSON.stringify(terms).slice(0, 200));
  }
}

// ────────────────────────────── 14. POST_BOUNTY REFUNDS ON REJECT
head(14, "a refused bounty REFUNDS — the payable rule, one contract removed");
{
  const before = await cOutsider.read.getBalance({ address: cOutsider.account.address });
  const out = await cOutsider.send("post_bounty", ["", "Python", "EXPERT"], GEN);
  const body = returnedJson(out);
  check("the transaction succeeded", out.ok === true, out.status);
  check("the return says ok:false", !out.returnReadable || body?.ok === false, JSON.stringify(body).slice(0, 120));
  let recovered = false;
  for (let i = 0; i < 30 && !recovered; i++) {
    await sleep(4000);
    const now = await cOutsider.read.getBalance({ address: cOutsider.account.address });
    if (now >= before - GEN / 100n) recovered = true;
  }
  check("the reward came back", recovered);

  const none = await cOutsider.send("post_bounty", ["Anyone at all", "Python", "NONE"], GEN);
  const nbody = returnedJson(none);
  check("min_level NONE is refused (it would let anybody claim)", !none.returnReadable || nbody?.ok === false,
    JSON.stringify(nbody).slice(0, 120));
}

// ──────────────────────────────────── 15. LISTINGS AND STATS
head(15, "listings and stats reflect what happened");
{
  const stats = await owner.viewJson("get_stats");
  check("verifications were recorded", stats.total_verifications > 0, String(stats.total_verifications));
  check("resolved + pending + stalled accounts for every verification",
    stats.resolved + stats.pending + stalledSafe(stats) === stats.total_verifications,
    JSON.stringify(stats));
  check("users were indexed", stats.users_verified > 0, String(stats.users_verified));
  check("skills were indexed", stats.skills_verified > 0, String(stats.skills_verified));

  const byUser = await owner.viewJson("get_verifications_by_user", ["torvalds", 0, 10]);
  check("torvalds has verifications", byUser.total > 0, String(byUser.total));
  check("newest first", byUser.verifications.length < 2 ||
    byUser.verifications[0].verification_id > byUser.verifications[1].verification_id);
  const byUpper = await owner.viewJson("get_verifications_by_user", ["TORVALDS", 0, 10]);
  check("the user index is case-insensitive", byUpper.total === byUser.total);

  const bySkill = await owner.viewJson("get_verifications_by_skill", ["c", 0, 10]);
  check("the skill index answers", bySkill.total > 0, String(bySkill.total));
}
function stalledSafe(s) { return typeof s.stalled === "number" ? s.stalled : 0; }

// ────────────────────────────────────── 16. EVERY RECORD IS SELF-CONSISTENT
head(16, "every stored record agrees with its own evidence");
{
  const all = await owner.viewJson("get_verifications_by_user", ["torvalds", 0, 50]);
  const rows = all.verifications;
  let consistent = 0, checked = 0;
  const RANK = { NONE: 0, BEGINNER: 1, PROFICIENT: 2, EXPERT: 3 };
  for (const row of rows) {
    if (row.status !== "RESOLVED") continue;
    checked++;
    // The level must follow from the counts. A record carrying a verdict its
    // own evidence does not support is the thing _apply exists to prevent.
    const bytes = BigInt(row.total_bytes);
    const expected = row.repo_count >= 5 && bytes >= 1000n ? "EXPERT"
      : row.repo_count >= 3 && bytes >= 500n ? "PROFICIENT"
      : row.repo_count >= 1 ? "BEGINNER" : "NONE";
    if (row.level === expected) consistent++;
    else console.log(`         MISMATCH id=${row.verification_id} level=${row.level} expected=${expected} repos=${row.repo_count} bytes=${row.total_bytes}`);
    check(`id ${row.verification_id}: rank matches the level`, row.level_rank === RANK[row.level]);
    check(`id ${row.verification_id}: RESOLVED carries a hash`, row.content_hash.length === 16, row.content_hash);
  }
  check(`every resolved record's level follows from its counts (${consistent}/${checked})`, consistent === checked);
}

console.log(`\n══════════════════════════════════════════════════════════════════════`);
console.log(`  ${passed} passed   ${failed} failed   ${notes} notes`);
if (failures.length) { console.log(`\n  failures:`); for (const f of failures) console.log(`    - ${f}`); }
console.log(`══════════════════════════════════════════════════════════════════════`);
process.exit(failed ? 1 : 0);
