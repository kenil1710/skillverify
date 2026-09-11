/**
 * Prove the identity gate ON CHAIN, with real transactions.
 *
 *   node prove_identity_gate.mjs                       # uses test/.deployed.json
 *   node prove_identity_gate.mjs --oracle=0x… --consumer=0x…
 *
 * The offline suite proves the gate against a storage stub and the deploy script
 * proves it read-only. Neither sends a transaction, and "the contract says it
 * binds claimants" is not the same claim as "a wallet that is not the registered
 * one tried to take the money and could not".
 *
 * Six writes, in the order a thief would actually meet them:
 *
 *   1. ALICE registers a username                 -> bound, permanently
 *   2. BOB tries to register the same one         -> refused, binding unmoved
 *   3. ALICE posts a bounty                       -> 1 GEN locked
 *   4. BOB claims it quoting ALICE's username     -> REFUSED, nothing moves
 *   5. BOB verifies that username himself         -> allowed, and earns nothing
 *   6. BOB claims again as the fresh verified_by  -> REFUSED AGAIN
 *
 * Step 6 is the one worth the gas. Binding a claim to `verified_by` — the wallet
 * that paid for the verification — is the obvious fix and it is wrong: the
 * consumer reads the NEWEST resolved record, so a thief becomes verified_by by
 * paying a fee. This script makes that attack on a live contract and watches it
 * fail.
 *
 * Studio Dev only: the fee policy is enabled here, so every write carries an
 * explicit `fees` object. See deploy_studiodev.mjs.
 */
import { createClient, createAccount } from "genlayer-js-rc";
import { studioDevnet } from "genlayer-js-rc/chains";
import { readFileSync } from "node:fs";

const argOf = (name, fallback = null) => {
  const found = process.argv.find((a) => a.startsWith(`--${name}=`));
  return found ? found.slice(name.length + 3) : fallback;
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const RPC = studioDevnet.rpcUrls.default.http[0];

const deployed = JSON.parse(readFileSync(new URL("./.deployed.json", import.meta.url), "utf8"));
const ORACLE = argOf("oracle", deployed?.SkillVerify?.address);
const CONSUMER = argOf("consumer", deployed?.SkillConsumer?.address);
if (!ORACLE || !CONSUMER) throw new Error("no addresses — pass --oracle= and --consumer=");

const accounts = JSON.parse(readFileSync(new URL("./.accounts.json", import.meta.url), "utf8"));
const USERNAME = argOf("username", "torvalds");
const SKILL = argOf("skill", "C");
const REWARD = 10n ** 18n;

const read = createClient({ chain: studioDevnet });
const clientOf = (role) => createClient({ chain: studioDevnet, account: createAccount(accounts[role].key) });
const ALICE = clientOf("alice");
const BOB = clientOf("bob");

async function fund(address) {
  await fetch(RPC, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      jsonrpc: "2.0", id: 1, method: "sim_fundAccount",
      params: [address, "0x" + (400n * 10n ** 18n).toString(16)],
    }),
  });
}

const view = async (address, functionName, args = []) => {
  for (let attempt = 1; ; attempt++) {
    try {
      return await read.readContract({ address, functionName, args });
    } catch (e) {
      if (attempt >= 4) throw e;
      await sleep(3000 * attempt);
    }
  }
};

/**
 * Send a write and wait for it to settle. NEVER THROWS on a contract-level
 * refusal — a refusal IS the result under test here, and three of the six steps
 * expect one.
 */
async function send(wallet, address, functionName, args, value = 0n) {
  // estimateTransactionFeesForWrite, NOT estimateTransactionFees. A claim that
  // succeeds EMITS A MESSAGE — the value transfer to the claimant — and the fee
  // policy funds messages from a per-message allocation that a bare fee
  // estimate does not contain. Without one the transaction is ACCEPTED, the
  // execution errors with `fee no_matching_allocation # external`, and the
  // bounty is simply still OPEN afterwards: no revert reason, no transfer, and
  // a receipt that says ACCEPTED. This simulates the call first and derives the
  // allocation from what it actually emits.
  let fees;
  try {
    fees = await wallet.estimateTransactionFeesForWrite({ address, functionName, args, value });
  } catch {
    fees = await wallet.estimateTransactionFees({});
  }
  let hash;
  try {
    hash = await wallet.writeContract({ address, functionName, args, value, fees });
  } catch (e) {
    return { ok: false, failure: String(e.message).slice(0, 300) };
  }
  const started = Date.now();
  for (;;) {
    let tx = null;
    try {
      tx = await read.getTransaction({ hash });
    } catch { /* blind poll */ }
    const status = String(tx?.statusName ?? tx?.status ?? "");
    if (["ACCEPTED", "FINALIZED", "UNDETERMINED", "CANCELED"].includes(status)) {
      const named = tx?.txExecutionResultName ?? null;
      const raw = tx?.consensus_data?.leader_receipt?.[0]?.result ?? tx?.result ?? null;
      // The contract answers with a JSON string; the SDK hands it back in
      // different shapes depending on the receipt, so every plausible one is
      // tried before giving up on reading the reason.
      let payload = null;
      for (const candidate of [raw, tx?.returnValue, tx?.data?.result]) {
        if (typeof candidate === "string") {
          try { payload = JSON.parse(candidate); break; } catch { /* not it */ }
        } else if (candidate && typeof candidate === "object" && candidate.ok !== undefined) {
          payload = candidate; break;
        }
      }
      return { ok: named !== "FINISHED_WITH_ERROR" && status !== "CANCELED" && status !== "UNDETERMINED",
        status, named, payload, hash, seconds: ((Date.now() - started) / 1000).toFixed(0) };
    }
    if (Date.now() - started > 300_000) return { ok: false, failure: "never settled", hash };
    await sleep(2000);
  }
}

const results = [];
function check(label, ok, detail = "") {
  results.push(ok);
  console.log(`  ${ok ? "ok  " : "FAIL"} ${label}${detail ? `  (${detail})` : ""}`);
}

console.log(`SkillVerify    ${ORACLE}`);
console.log(`SkillConsumer  ${CONSUMER}`);
console.log(`alice ${accounts.alice.address}\nbob   ${accounts.bob.address}\n`);
await fund(accounts.alice.address);
await fund(accounts.bob.address);

// ── 1. ALICE registers the username ────────────────────────────────────────
console.log(`1. alice registers "${USERNAME}"`);
let out = await send(ALICE, ORACLE, "register_identity", [USERNAME]);
console.log(`   ${out.status ?? out.failure} in ${out.seconds ?? "?"}s`);
let identity = JSON.parse(await view(ORACLE, "get_identity", [USERNAME]));
check("the username is bound to alice",
  identity.registered === true
  && String(identity.identity_owner).toLowerCase() === accounts.alice.address.toLowerCase(),
  JSON.stringify(identity));
check("owns_identity agrees", (await view(ORACLE, "owns_identity", [USERNAME, accounts.alice.address])) === true);
check("and refuses bob", (await view(ORACLE, "owns_identity", [USERNAME, accounts.bob.address])) === false);

// ── 2. BOB tries to take it ────────────────────────────────────────────────
console.log(`\n2. bob tries to register the same username`);
out = await send(BOB, ORACLE, "register_identity", [USERNAME]);
const after = JSON.parse(await view(ORACLE, "get_identity", [USERNAME]));
check("the binding did not move", JSON.stringify(after) === JSON.stringify(identity), JSON.stringify(after));

// ── 3. a funded bounty ─────────────────────────────────────────────────────
console.log(`\n3. alice posts a ${Number(REWARD) / 1e18} GEN bounty in ${SKILL}`);
out = await send(ALICE, CONSUMER, "post_bounty", [`Port the ${SKILL} driver`, SKILL, "BEGINNER"], REWARD);
console.log(`   ${out.status ?? out.failure} in ${out.seconds ?? "?"}s`);
const book = JSON.parse(await view(CONSUMER, "get_bounties", [0, 50]));
const bounty = book.bounties[0];
check("the bounty is open and funded", Boolean(bounty) && bounty.status === "OPEN" && bounty.reward === String(REWARD),
  JSON.stringify(bounty?.status) + " " + bounty?.reward);
const bountyId = bounty?.bounty_id;

// ── 4. the theft, before any verification exists ───────────────────────────
console.log(`\n4. bob claims it quoting alice's username`);
let dry = JSON.parse(await view(CONSUMER, "can_claim", [bountyId, USERNAME, accounts.bob.address]));
check("can_claim refuses bob up front", dry.ok === false, dry.reason);
out = await send(BOB, CONSUMER, "claim_bounty", [bountyId, USERNAME]);
let row = JSON.parse(await view(CONSUMER, "get_bounty", [bountyId]));
check("the bounty is still OPEN after bob's claim", row.status === "OPEN", row.status);
check("nothing was paid", row.claimant === "0x0000000000000000000000000000000000000000", row.claimant);

// ── 5. bob buys a verification for a username he does not own ──────────────
console.log(`\n5. bob verifies "${USERNAME}" himself — permissionless, and it earns him nothing`);
out = await send(BOB, ORACLE, "verify_skill", [USERNAME, SKILL]);
console.log(`   ${out.status ?? out.failure} in ${out.seconds ?? "?"}s`);
const latest = JSON.parse(await view(ORACLE, "get_latest", [USERNAME, SKILL]));
console.log(`   get_latest: found=${latest.found} level=${latest.level ?? "-"} status=${latest.status ?? "-"}`);
if (latest.found) {
  check("verified_by is bob — he paid for it",
    String(latest.verified_by).toLowerCase() === accounts.bob.address.toLowerCase(), String(latest.verified_by));
  check("identity_owner is still alice",
    String(latest.identity_owner).toLowerCase() === accounts.alice.address.toLowerCase(), String(latest.identity_owner));
} else {
  console.log(`   note: no resolved verification (GitHub's shared rate-limit bucket, or a PENDING record).`);
  console.log(`   Steps 4 and 6 hold regardless — the identity gate is checked before the level.`);
}

// ── 6. THE ATTACK THE OBVIOUS FIX WOULD HAVE ALLOWED ───────────────────────
console.log(`\n6. bob claims again, now that he is the wallet that paid for the verification`);
dry = JSON.parse(await view(CONSUMER, "can_claim", [bountyId, USERNAME, accounts.bob.address]));
check("can_claim still refuses him", dry.ok === false, dry.reason);
out = await send(BOB, CONSUMER, "claim_bounty", [bountyId, USERNAME]);
row = JSON.parse(await view(CONSUMER, "get_bounty", [bountyId]));
check("the bounty survived a verified_by thief", row.status === "OPEN", row.status);

// ── and the rightful owner, if the oracle answered ─────────────────────────
if (latest.found && latest.level && latest.level !== "NONE") {
  console.log(`\n7. alice — the registered wallet — claims`);
  dry = JSON.parse(await view(CONSUMER, "can_claim", [bountyId, USERNAME, accounts.alice.address]));
  check("can_claim says yes for alice", dry.ok === true, dry.reason ?? dry.level);
  out = await send(ALICE, CONSUMER, "claim_bounty", [bountyId, USERNAME]);
  console.log(`   ${out.status ?? out.failure} in ${out.seconds ?? "?"}s`);
  row = JSON.parse(await view(CONSUMER, "get_bounty", [bountyId]));
  check("the bounty was paid to alice",
    row.status === "CLAIMED" && String(row.claimant).toLowerCase() === accounts.alice.address.toLowerCase(),
    `${row.status} ${row.claimant}`);
} else {
  console.log(`\n7. skipped — no resolved verification to claim against.`);
  console.log(`   alice can withdraw the bounty; it is not stuck.`);
}

const passed = results.filter(Boolean).length;
console.log(`\n${passed}/${results.length} on-chain checks passed`);
process.exit(passed === results.length ? 0 : 1);
