/**
 * Deploy SkillVerify + SkillConsumer.
 *
 *   node deploy.mjs                                     # studionet
 *   node deploy.mjs --network=studiodev                 # chain 61997, v0.6 runner
 *   node deploy.mjs --network=bradbury --keystore=mywallet
 *   node deploy.mjs --network=bradbury --keystore=mywallet --oracle=0x…  # consumer only
 *
 * Deploys the BUILD ARTIFACTS, never the readable sources, so what is on chain
 * is byte-identical to what deployments.json records a checksum for.
 *
 * WHICH ARTIFACTS depends on the network, and getting it wrong deploys cleanly
 * and then fails at the first storage access. Studio Dev runs the v0.6 runner,
 * whose API surface differs from the v0.3 sources in contracts/ — those go
 * through tools/to_v06.py first and build/v06/*.v06.py is what lands there.
 *
 * WHO SIGNS: without --keystore the plaintext `client` account in
 * .accounts.json signs, which is fine on gasless Studionet but holds no gas on
 * Bradbury. --keystore=<name> unlocks a real GenLayer CLI wallet instead
 * (password from GENLAYER_KEYSTORE_PASSWORD, never argv). The signer becomes
 * the OWNER of both contracts.
 */
import { createClient, createAccount } from "genlayer-js";
import { readFileSync, writeFileSync } from "node:fs";
import { CHAINS, accounts, argOf, contractAddressOf, fundOnStudio, outcomeOf, retry, sleep } from "./harness.mjs";
import { resolveSigner } from "./keystore.mjs";

const networkName = argOf("network", "studionet");
const chain = CHAINS[networkName];
if (!chain) throw new Error(`unknown network ${networkName}`);

const acc = accounts();
const signer = resolveSigner(process.argv, new URL("./.accounts.json", import.meta.url));
const account = createAccount(signer.key);
const wallet = createClient({ chain, account });
const read = createClient({ chain });

const V06 = networkName === "studiodev";
const ORACLE_SRC = new URL(V06 ? "../build/v06/SkillVerify.v06.py" : "../build/SkillVerify.min.py", import.meta.url);
const CONSUMER_SRC = new URL(V06 ? "../build/v06/SkillConsumer.v06.py" : "../build/SkillConsumer.min.py", import.meta.url);
const FEE = Number(argOf("fee", "0"));

const WALLET_FUNDING = 60n * 10n ** 18n;
const CLIENT_FUNDING = 400n * 10n ** 18n;
const MIN_DEPLOY_BALANCE = 1n * 10n ** 18n;

async function preflight() {
  console.log(`==> signing as ${signer.label}`);
  const oracleBytes = readFileSync(ORACLE_SRC).length;
  const consumerBytes = readFileSync(CONSUMER_SRC).length;
  console.log(`  artifacts: SkillVerify ${oracleBytes} bytes, SkillConsumer ${consumerBytes} bytes`);
  console.log(`  runner:    ${readFileSync(ORACLE_SRC, "utf8").split("\n").find((l) => l.includes("Depends"))?.trim()}`);
  if (V06 && !readFileSync(ORACLE_SRC, "utf8").includes("gl.storage.TreeMap")) {
    throw new Error("studiodev needs the v0.6 artifacts — run: python3 tools/to_v06.py");
  }
  // 37,658 bytes is the largest artifact confirmed on Bradbury across the
  // previous projects; 59,278 is a measured refusal. Both of these are well
  // under the confirmed figure, so this is a note rather than a gate.
  if (oracleBytes > 37_658) {
    console.log(`  !! ${oracleBytes} bytes exceeds the largest artifact previously confirmed on Bradbury (37,658)`);
  }
  if (chain.isStudio) return;
  const balance = await retry(() => read.getBalance({ address: account.address }), { label: "deployer balance" });
  const gen = (Number(balance) / 1e18).toFixed(4);
  console.log(`  balance ${gen} GEN on ${networkName}`);
  if (balance < MIN_DEPLOY_BALANCE) {
    throw new Error(`${account.address} holds ${gen} GEN — not enough for two deploys on ${networkName}.`);
  }
}

async function fundAll() {
  if (!chain.isStudio) {
    console.log("not Studionet — fund these addresses manually before running e2e");
    for (const [role, v] of Object.entries(acc)) console.log(`  ${role.padEnd(10)} ${v.address}`);
    return;
  }
  console.log("==> funding wallets from the Studio faucet");
  for (const [role, v] of Object.entries(acc)) {
    const ok = await fundOnStudio(chain, v.address, role === "client" ? CLIENT_FUNDING : WALLET_FUNDING);
    console.log(`  ${ok ? "ok  " : "FAIL"} ${role.padEnd(10)} ${v.address}`);
    await sleep(200);
  }
}

async function deploy(url, args, label) {
  // A constructor argument that is undefined or null does NOT fail at encode
  // time — it is serialised, the constructor receives it, and the deploy
  // reverts on chain after the gas is spent.
  args.forEach((a, i) => {
    if (a === undefined || a === null) {
      throw new Error(`${label}: constructor arg ${i} is ${String(a)} — refusing to submit a deploy that will revert`);
    }
  });
  const code = readFileSync(url);
  console.log(`\n==> deploying ${label} (${code.length} bytes)`);
  let hash;
  for (let attempt = 1; ; attempt++) {
    try {
      hash = await wallet.deployContract({ code, args });
      break;
    } catch (e) {
      if (attempt >= 4) throw e;
      console.log(`  submit attempt ${attempt} rejected, retrying: ${String(e.message).slice(0, 160)}`);
      await sleep(15_000 * attempt);
    }
  }
  const deadline = chain.isStudio ? 300_000 : 900_000;
  const started = Date.now();
  for (;;) {
    let tx = null;
    try {
      tx = await retry(() => read.getTransaction({ hash }), { attempts: 4, label: `${label} poll` });
    } catch { /* blind poll — absence of evidence is not evidence of failure */ }
    const out = outcomeOf(tx);
    if (out.settled) {
      if (!out.ok) {
        // ACCEPTED is a CONSENSUS verdict — the validators agreed on what
        // happened — and says nothing about whether what they agreed on was a
        // success. Both halves are printed so an errored deploy is never read
        // as a working one because the word ACCEPTED appears.
        console.log(`  !! ${label} REVERTED (consensus ${out.status}, execution ${out.named ?? out.exec ?? "ERROR"})`);
        console.log(`     ${out.revertReason || out.stderr.slice(0, 500) || "no revert reason reported"}`);
        throw new Error(`${label} deploy failed (tx ${hash})`);
      }
      const address = contractAddressOf(tx);
      if (!address) throw new Error(`${label}: deploy settled ok but returned no address (tx ${hash})`);
      console.log(`  ${label} at ${address}  (${((Date.now() - started) / 1000).toFixed(0)}s, tx ${hash})`);
      return { address, hash };
    }
    if (Date.now() - started > deadline) throw new Error(`${label} deploy never settled`);
    await sleep(chain.isStudio ? 1500 : 5000);
  }
}

await preflight();
await fundAll();

// --oracle=<address> reuses a SkillVerify that is ALREADY LIVE and deploys only
// the consumer against it. The pair goes out in two transactions: when the
// second fails, redeploying both would abandon a perfectly good first contract.
const reuseOracle = argOf("oracle", null);
let oracle;
if (reuseOracle) {
  console.log(`\n==> reusing SkillVerify at ${reuseOracle}`);
  const probe = JSON.parse(await retry(
    () => read.readContract({ address: reuseOracle, functionName: "get_config", args: [] }),
    { label: "reused oracle get_config" }));
  console.log(`  responds to get_config — owner ${probe.owner}, paused ${probe.paused}`);
  oracle = { address: reuseOracle, hash: argOf("oracle-tx", null), reused: true };
} else {
  oracle = await deploy(ORACLE_SRC, [FEE], "SkillVerify");
}

const consumer = await deploy(CONSUMER_SRC, [oracle.address], "SkillConsumer");

writeFileSync(new URL("./.deployed.json", import.meta.url), JSON.stringify({
  network: networkName,
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
const view = (address, functionName, args = []) =>
  retry(() => read.readContract({ address, functionName, args }), { label: functionName });

const cfg = JSON.parse(await view(oracle.address, "get_config"));
const viaConsumer = JSON.parse(await view(consumer.address, "get_oracle_config"));
const terms = JSON.parse(await view(consumer.address, "get_terms"));
const identity = JSON.parse(await view(oracle.address, "get_identity", ["nobody-at-all-here"]));
const zeroOwns = await view(oracle.address, "owns_identity",
  ["nobody-at-all-here", "0x0000000000000000000000000000000000000000"]);

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
  ["consumer points at this oracle", String(terms.oracle).toLowerCase() === oracle.address.toLowerCase(), terms.oracle],
  // The ladder is duplicated in the consumer so the oracle cannot silently
  // redefine what a bounty pays for. A mismatch has to be caught HERE, at
  // deploy time, and not at the first claim.
  ["both ladders agree", JSON.stringify(terms.levels) === JSON.stringify(cfg.levels), JSON.stringify(terms.levels)],
  ["consumer reads the same oracle", String(viaConsumer.owner ?? "").toLowerCase() === String(cfg.owner).toLowerCase(), String(viaConsumer.owner)],
  // THE IDENTITY BINDING, asserted at deploy time. A consumer wired to an
  // oracle that cannot bind a claimant refuses every claim, and a consumer that
  // does not bind pays whoever asks. Both halves have to be live, and both are
  // read-only facts the contracts publish about themselves.
  ["the oracle can bind an identity", cfg.identity_binding === "register_identity", String(cfg.identity_binding)],
  ["the consumer binds its claimants", terms.claims_are_identity_bound === true, String(terms.claims_are_identity_bound)],
  ["an unregistered username owns nothing", identity.registered === false && identity.identity_owner === "", JSON.stringify(identity)],
  ["owns_identity is false for the zero address", zeroOwns === false, String(zeroOwns)],
];

let bad = 0;
for (const [label, ok, got] of checks) {
  console.log(`  ${ok ? "ok  " : "FAIL"} ${label}${ok ? "" : `  (got ${got})`}`);
  if (!ok) bad++;
}
if (bad) throw new Error(`${bad} of ${checks.length} config checks failed — contracts are live but not as expected`);

console.log(`\n======================================================================`);
console.log(`  network         ${networkName}`);
console.log(`  owner           ${cfg.owner}`);
console.log(`  SkillVerify     ${oracle.address}`);
console.log(`  SkillConsumer   ${consumer.address}`);
console.log(`======================================================================`);
console.log(`\nwrote test/.deployed.json`);
console.log(chain.isStudio ? `next:  node e2e.mjs --network=${networkName}` : `fund the wallet roles on ${networkName} before running e2e`);
