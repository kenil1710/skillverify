/**
 * Deploy SkillVerify + SkillConsumer to Studio Dev (chain 61997).
 *
 *   node deploy_studiodev.mjs
 *   node deploy_studiodev.mjs --oracle=0x…        # consumer only, against a live oracle
 *
 * A SEPARATE SCRIPT FROM deploy.mjs, and the separation is not cosmetic.
 * Studio Dev needs two things the pinned client cannot do, and the first
 * attempt at this cost four reverted deploys before the reason surfaced:
 *
 *   THE FEE POLICY IS ENABLED AND THERE IS NO feeManagerContract. genlayer-js
 *   1.1.8 has no `fees` argument at all, so every transaction it builds carries
 *   an all-zero distribution and the consensus contract reverts it. The error
 *   says only "Transaction reverted: EVM tx … to consensus contract … was
 *   reverted" — nothing about fees, nothing about the code, and it looks
 *   exactly like a contract that does not compile. 2.0.0-rc.1 exposes
 *   `estimateFeesDistribution()`; it is installed alongside as `genlayer-js-rc`
 *   rather than replacing the pinned client, because deploy.mjs and e2e.mjs are
 *   proven against 1.1.8 on Studionet and Bradbury and this is not the week to
 *   re-prove them.
 *
 *   THE RUNNER IS v0.6, whose API surface differs from the v0.3 sources in
 *   contracts/. build/v06/*.v06.py is what lands here — produced by
 *   tools/to_v06.py, which is asserted below rather than trusted.
 *
 * Deploys the BUILD ARTIFACTS, never the readable sources, so what is on chain
 * is byte-identical to what deployments.json records a checksum for. The signer
 * becomes the OWNER of both contracts.
 */
import { createClient, createAccount } from "genlayer-js-rc";
import { studioDevnet } from "genlayer-js-rc/chains";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";

const argOf = (name, fallback = null) => {
  const found = process.argv.find((a) => a.startsWith(`--${name}=`));
  return found ? found.slice(name.length + 3) : fallback;
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const RPC = studioDevnet.rpcUrls.default.http[0];
const ORACLE_SRC = new URL("../build/v06/SkillVerify.v06.py", import.meta.url);
const CONSUMER_SRC = new URL("../build/v06/SkillConsumer.v06.py", import.meta.url);
const FEE = Number(argOf("fee", "0"));
const FUNDING = 400n * 10n ** 18n;

const accounts = JSON.parse(readFileSync(new URL("./.accounts.json", import.meta.url), "utf8"));
const signer = accounts[argOf("role", "client")];
if (!signer?.key) throw new Error(`no key for role ${argOf("role", "client")} — run: node accounts.mjs`);

const account = createAccount(signer.key);
const wallet = createClient({ chain: studioDevnet, account });
const read = createClient({ chain: studioDevnet });

/**
 * The Studio faucet. THE AMOUNT MUST BE A HEX STRING: 400 GEN is 4e20, which
 * JSON.stringify writes as `4e+20`, and the node answers "amount must be a
 * positive integer" — after which the deploy fails for want of a deposit, which
 * reads as a problem with the contract and is not.
 */
async function fund(address, wei) {
  const res = await fetch(RPC, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: 1,
      method: "sim_fundAccount",
      params: [address, "0x" + BigInt(wei).toString(16)],
    }),
  });
  return Boolean((await res.json())?.result);
}

const sha = (url) => createHash("sha256").update(readFileSync(url)).digest("hex");

async function preflight() {
  console.log(`==> ${studioDevnet.name} (chain ${studioDevnet.id})`);
  console.log(`  signing as ${signer.address}`);
  for (const [label, url] of [["SkillVerify", ORACLE_SRC], ["SkillConsumer", CONSUMER_SRC]]) {
    const text = readFileSync(url, "utf8");
    // The v0.6 conversion is ASSERTED, not assumed. A v0.3 artifact deploys
    // clean here and then fails at the first storage access, which is the
    // expensive way to discover that tools/to_v06.py was never run.
    if (!text.includes("gl.storage.TreeMap")) {
      throw new Error(`${label} is not a v0.6 artifact — run: python3 tools/to_v06.py`);
    }
    console.log(`  ${label.padEnd(14)} ${readFileSync(url).length} bytes  sha256 ${sha(url).slice(0, 16)}…`);
  }
  console.log(`  runner         ${readFileSync(ORACLE_SRC, "utf8").split("\n")[1].trim()}`);

  const ok = await fund(signer.address, FUNDING);
  const balance = await read.getBalance({ address: account.address });
  console.log(`  faucet ${ok ? "ok" : "FAILED"} — balance ${(Number(balance) / 1e18).toFixed(2)} GEN`);
  if (balance === 0n) throw new Error("the deployer holds nothing; a zero-balance deploy cannot pay its deposit");
}

async function deploy(url, args, label) {
  // A constructor argument that is undefined or null does NOT fail at encode
  // time — it is serialised, the constructor receives it, and the deploy
  // reverts on chain after the deposit is spent.
  args.forEach((a, i) => {
    if (a === undefined || a === null) {
      throw new Error(`${label}: constructor arg ${i} is ${String(a)} — refusing to submit a deploy that will revert`);
    }
  });
  const code = readFileSync(url);
  // Without this the SDK sends an all-zero distribution and the consensus
  // contract refuses the transaction. See the header.
  //
  // estimateTransactionFees, NOT estimateFeesDistribution: the distribution
  // alone still carries feeValue 0 and the consensus contract answers
  // `FeeValueMustBeNonZero(1)`, which is a clearer error than the bare revert
  // and still not one that names fees as the problem unless you know. The full
  // object carries the ~0.1 GEN deposit alongside the caps.
  const fees = await wallet.estimateTransactionFees({});
  console.log(`  deposit ${(Number(fees.feeValue) / 1e18).toFixed(4)} GEN`);
  console.log(`\n==> deploying ${label} (${code.length} bytes)`);
  let hash;
  for (let attempt = 1; ; attempt++) {
    try {
      hash = await wallet.deployContract({ code, args, fees });
      break;
    } catch (e) {
      if (attempt >= 3) throw e;
      console.log(`  submit attempt ${attempt} rejected, retrying: ${String(e.message).slice(0, 200)}`);
      await sleep(10_000 * attempt);
    }
  }
  const started = Date.now();
  for (;;) {
    let tx = null;
    try {
      tx = await read.getTransaction({ hash });
    } catch { /* blind poll — absence of evidence is not evidence of failure */ }
    const status = tx?.statusName ?? tx?.status;
    const named = tx?.txExecutionResultName ?? null;
    const settled = ["ACCEPTED", "FINALIZED", "UNDETERMINED", "CANCELED"].includes(String(status));
    if (settled) {
      // ACCEPTED is a CONSENSUS verdict — the validators agreed on what
      // happened — and says nothing about whether what they agreed on was a
      // success. Both halves are printed so an errored deploy is never read as
      // a working one because the word ACCEPTED appears.
      const ok = named !== "FINISHED_WITH_ERROR" && String(status) !== "CANCELED"
        && String(status) !== "UNDETERMINED";
      if (!ok) {
        console.log(`  !! ${label} FAILED (consensus ${status}, execution ${named ?? "unknown"})`);
        console.log(`     ${JSON.stringify(tx?.consensus_data?.leader_receipt?.[0]?.result ?? {}).slice(0, 500)}`);
        throw new Error(`${label} deploy failed (tx ${hash})`);
      }
      const address = tx?.data?.contract_address ?? tx?.txDataDecoded?.contractAddress
        ?? tx?.contract_address ?? null;
      if (!address) throw new Error(`${label}: deploy settled ok but returned no address (tx ${hash})`);
      console.log(`  ${label} at ${address}  (${((Date.now() - started) / 1000).toFixed(0)}s, tx ${hash})`);
      return { address, hash };
    }
    if (Date.now() - started > 300_000) throw new Error(`${label} deploy never settled (tx ${hash})`);
    await sleep(2000);
  }
}

await preflight();

// --oracle=<address> reuses a SkillVerify that is ALREADY LIVE and deploys only
// the consumer against it. The pair goes out in two transactions: when the
// second fails, redeploying both would abandon a perfectly good first contract.
const reuse = argOf("oracle", null);
const oracle = reuse
  ? { address: reuse, hash: argOf("oracle-tx", null), reused: true }
  : await deploy(ORACLE_SRC, [FEE], "SkillVerify");
const consumer = await deploy(CONSUMER_SRC, [oracle.address], "SkillConsumer");

writeFileSync(new URL("./.deployed.json", import.meta.url), JSON.stringify({
  network: "studiodev",
  deployedAt: new Date().toISOString(),
  SkillVerify: oracle,
  SkillConsumer: consumer,
}, null, 2) + "\n");

// --------------------------------------------------------------------------
// Verify what actually landed. A settled deploy says the code was ACCEPTED, not
// that the contract answers — and the consumer is constructed with the oracle's
// address, so reading the config back THROUGH the consumer is the only cheap
// proof that the two are wired to each other rather than each merely existing.
console.log(`\n==> verifying`);
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

const cfg = JSON.parse(await view(oracle.address, "get_config"));
const stats = JSON.parse(await view(oracle.address, "get_stats"));
const terms = JSON.parse(await view(consumer.address, "get_terms"));
const viaConsumer = JSON.parse(await view(consumer.address, "get_oracle_config"));
const report = JSON.parse(await view(consumer.address, "get_skill_report", ["torvalds", "C"]));
const identity = JSON.parse(await view(oracle.address, "get_identity", ["torvalds"]));
const ZERO = "0x0000000000000000000000000000000000000000";

const checks = [
  ["four levels, lowest first", JSON.stringify(cfg.levels) === '["NONE","BEGINNER","PROFICIENT","EXPERT"]', JSON.stringify(cfg.levels)],
  ["six axis values", JSON.stringify(cfg.axis_values) === '["EXPERT","PROFICIENT","BEGINNER","NONE","NO_SUCH_USER","UNAVAILABLE"]', JSON.stringify(cfg.axis_values)],
  ["three statuses", JSON.stringify(cfg.statuses) === '["PENDING","RESOLVED","STALLED"]', JSON.stringify(cfg.statuses)],
  ["fee is as deployed", Number(cfg.fee) === FEE, String(cfg.fee)],
  ["not paused", cfg.paused === false, String(cfg.paused)],
  ["owner is the signer", String(cfg.owner).toLowerCase() === account.address.toLowerCase(), cfg.owner],
  ["forks are excluded", cfg.forks_counted === false, String(cfg.forks_counted)],
  ["bytes basis is declared", cfg.bytes_basis === "github_repo_size_kb", String(cfg.bytes_basis)],
  ["source is the search index", String(cfg.source).includes("/search/repositories"), String(cfg.source)],
  ["cooldown is 300s", Number(cfg.cooldown_seconds) === 300, String(cfg.cooldown_seconds)],
  ["EXPERT threshold is 5 repos", cfg.thresholds?.EXPERT?.repos === 5, JSON.stringify(cfg.thresholds?.EXPERT)],
  ["views do not revert for an unknown id",
    JSON.parse(await view(oracle.address, "get_verification", [999999])).found === false, "found"],
  ["is_verified answers false rather than raising",
    (await view(oracle.address, "is_verified", ["nobody-at-all-here", "Cobol", "BEGINNER"])) === false, "is_verified"],
  ["consumer points at this oracle", String(terms.oracle).toLowerCase() === oracle.address.toLowerCase(), terms.oracle],
  // The ladder is duplicated in the consumer so the oracle cannot silently
  // redefine what a bounty pays for. A mismatch has to be caught HERE, at
  // deploy time, and not at the first claim.
  ["both ladders agree", JSON.stringify(terms.levels) === JSON.stringify(cfg.levels), JSON.stringify(terms.levels)],
  ["consumer reads the same oracle", String(viaConsumer.owner ?? "").toLowerCase() === String(cfg.owner).toLowerCase(), String(viaConsumer.owner)],
  // THE CROSS-BOUNDARY CHECK THAT ACTUALLY BITES. A consumer whose oracle call
  // is broken answers "oracle unreachable" and looks identical on `found`,
  // which is how a dead dependency shipped here once already.
  ["the consumer's oracle read reaches the contract",
    report.reason !== "oracle unreachable", String(report.reason)],

  // ── THE IDENTITY BINDING, read-only and live.
  ["the oracle can bind an identity", cfg.identity_binding === "register_identity", String(cfg.identity_binding)],
  ["the consumer binds its claimants", terms.claims_are_identity_bound === true, String(terms.claims_are_identity_bound)],
  ["no identity is registered yet", Number(stats.identities_registered) === 0, String(stats.identities_registered)],
  ["an unregistered username owns nothing",
    identity.registered === false && identity.identity_owner === "", JSON.stringify(identity)],
  ["owns_identity is false for the zero address",
    (await view(oracle.address, "owns_identity", ["torvalds", ZERO])) === false, "owns_identity"],
  ["is_verified_identity refuses an unbound claimant",
    (await view(oracle.address, "is_verified_identity", ["torvalds", "C", "NONE", signer.address])) === false, "is_verified_identity"],
];

let bad = 0;
for (const [label, ok, got] of checks) {
  console.log(`  ${ok ? "ok  " : "FAIL"} ${label}${ok ? "" : `  (got ${got})`}`);
  if (!ok) bad++;
}
if (bad) throw new Error(`${bad} of ${checks.length} config checks failed — contracts are live but not as expected`);

console.log(`\n======================================================================`);
console.log(`  network         studiodev (chain ${studioDevnet.id})`);
console.log(`  owner           ${cfg.owner}`);
console.log(`  SkillVerify     ${oracle.address}`);
console.log(`  SkillConsumer   ${consumer.address}`);
console.log(`  checks          ${checks.length}/${checks.length}`);
console.log(`======================================================================`);
console.log(`\nwrote test/.deployed.json`);
