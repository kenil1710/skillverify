/**
 * Probe round 3 — the escape from the shared bucket.
 *
 * Round 2 measured the hard constraint: every validator egresses from ONE IP
 * (44.198.152.104) into GitHub's 60-requests-per-hour unauthenticated bucket,
 * and round 1's repo walk drained all 60. So the contract cannot walk repos.
 * This round prices the two ways out.
 *
 *   node probe3.mjs [--network=studionet] [--address=0x…]
 */
import { createClient, createAccount } from "genlayer-js";
import { readFileSync, writeFileSync } from "node:fs";
import { CHAINS, accounts, argOf, contractAddressOf, fundOnStudio, outcomeOf, retry, sleep } from "./harness.mjs";

const networkName = argOf("network", "studionet");
const chain = CHAINS[networkName];
if (!chain) throw new Error(`unknown network ${networkName}`);
const acc = accounts();
const account = createAccount(acc.client.key);
const wallet = createClient({ chain, account });
const read = createClient({ chain });
const SRC = new URL("../contracts/_render_probe.py", import.meta.url);
const findings = {};

async function deployProbe() {
  const reuse = argOf("address", null);
  if (reuse) { console.log(`==> reusing probe at ${reuse}`); return reuse; }
  await fundOnStudio(chain, account.address, 100n * 10n ** 18n);
  const code = readFileSync(SRC);
  console.log(`==> deploying probe (${code.length} bytes)`);
  const hash = await retry(() => wallet.deployContract({ code, args: [] }), { label: "deploy" });
  const started = Date.now();
  for (;;) {
    const tx = await retry(() => read.getTransaction({ hash }), { attempts: 4, label: "deploy poll" }).catch(() => null);
    const out = outcomeOf(tx);
    if (out.settled) {
      if (!out.ok) throw new Error(`deploy failed: ${out.revertReason || out.stderr.slice(0, 400)}`);
      const a = contractAddressOf(tx); console.log(`  probe at ${a}\n`); return a;
    }
    if (Date.now() - started > 300_000) throw new Error("deploy never settled");
    await sleep(1500);
  }
}
const address = await deployProbe();

async function send(functionName, args) {
  const hash = await retry(() => wallet.writeContract({ address, functionName, args, value: 0n }), { label: functionName });
  const started = Date.now();
  for (;;) {
    const tx = await retry(() => read.getTransaction({ hash }), { attempts: 4, label: `${functionName} poll` }).catch(() => null);
    const out = outcomeOf(tx);
    if (out.settled) return { ...out, hash, seconds: (Date.now() - started) / 1000 };
    if (Date.now() - started > 400_000) return { ...outcomeOf(null), status: "UNSETTLED", hash };
    await sleep(1500);
  }
}
const report = async () => retry(() => read.readContract({ address, functionName: "get_report", args: [] }), { label: "get_report" });
async function experiment(label, fn, args) {
  process.stdout.write(`==> ${label}\n`);
  const out = await send(fn, args);
  const und = out.status === "UNDETERMINED";
  console.log(`    ${und ? "UNDETERMINED (validators disagreed)" : out.ok ? "COMMITTED (validators agreed)" : `FAILED ${out.status}`}  ${out.seconds ? out.seconds.toFixed(0) + "s" : ""}`);
  if (!out.ok && !und) console.log(`    ${out.revertReason || out.stderr.slice(0, 300) || ""}`);
  let body = null;
  if (out.ok) { const raw = await report(); try { body = JSON.parse(raw); } catch { body = raw; } }
  findings[label] = { agreed: out.ok, undetermined: und, status: out.status, report: body };
  return findings[label];
}

// -------------------------------------------- 1. EVERY BUCKET, NOT JUST core
const all = await experiment("rate_limit: all resources", "probe_rate_all", ["https://api.github.com/rate_limit"]);
if (all.report) for (const [k, v] of Object.entries(all.report)) if (k !== "status") console.log(`    ${k.padEnd(26)} ${v}`);

// ------------------------------------------------------- 2. THE SEARCH INDEX
for (const [user, skill] of [["torvalds", "C"], ["gvanrossum", "Python"], ["kenil1710", "JavaScript"], ["torvalds", "Haskell"]]) {
  const f = await experiment(`search:${user}/${skill}`, "probe_search", [user, skill, false]);
  const L = f.report?.leader;
  if (L) {
    console.log(`    status=${L.status} level=${L.level} total_count=${L.total_count} returned=${L.returned} forks=${L.forks} bytes=${L.total_bytes} incomplete=${L.incomplete}`);
    if (L.top) console.log(`    top=${JSON.stringify(L.top)}`);
    if (L.head) console.log(`    head=${String(L.head).slice(0, 200)}`);
  }
}

// ---------------------------------------------------- 3. DO FORKS COME BACK?
const withForks = await experiment("search:torvalds/C +fork:true", "probe_search", ["torvalds", "C", true]);
if (withForks.report?.leader) {
  const L = withForks.report.leader;
  console.log(`    status=${L.status} level=${L.level} total_count=${L.total_count} returned=${L.returned} forks=${L.forks} bytes=${L.total_bytes}`);
}

// -------------------------------- 4. MAY THE RECORD CARRY THE EVIDENCE TOO?
const strict = await experiment("search_strict:torvalds/C", "probe_search_strict", ["torvalds", "C"]);
if (strict.report?.leader) console.log(`    ${JSON.stringify(strict.report.leader)}`);
const strict2 = await experiment("search_strict:kenil1710/JavaScript", "probe_search_strict", ["kenil1710", "JavaScript"]);
if (strict2.report?.leader) console.log(`    ${JSON.stringify(strict2.report.leader)}`);

// ------------------------------------------------ 5. DRIFT ON THE RAW SEARCH
await experiment("drift:search", "probe_drift", ["https://api.github.com/search/repositories?q=user:torvalds+language:C&per_page=100&sort=updated"]);

// -------------------------------------------------------- 6. ungh.cc SHAPES
const ungh = await experiment("shape:ungh users/repos", "probe_shape", ["https://ungh.cc/users/torvalds/repos", 2]);
if (ungh.report) console.log("    " + JSON.stringify(ungh.report).slice(0, 1400));

// ----------------------------------- 7. NONSENSE INPUT MUST BE DETERMINISTIC
const junk = await experiment("search: bogus user", "probe_search", ["this-user-does-not-exist-skillverify-xyz", "Python", false]);
if (junk.report?.leader) console.log(`    ${JSON.stringify(junk.report.leader).slice(0, 400)}`);
const junk2 = await experiment("search: bogus language", "probe_search", ["torvalds", "Nonexistentlang", false]);
if (junk2.report?.leader) console.log(`    ${JSON.stringify(junk2.report.leader).slice(0, 400)}`);

writeFileSync(new URL("../docs/probe3_findings.json", import.meta.url), JSON.stringify({ address, network: networkName, at: new Date().toISOString(), findings }, null, 2) + "\n");
console.log(`\n==> wrote docs/probe3_findings.json  (probe at ${address})`);
