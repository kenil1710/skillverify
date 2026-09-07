/**
 * Probe round 2 — the question round 1 forced.
 *
 * Round 1's fan-out (1 repo-list call + 1 languages call per repo) scored
 * torvalds/C as EXPERT on its first transaction and then every single call
 * after it came back 403. That is either a shared bucket being exhausted or a
 * coincidence, and the two lead to opposite contracts. This round measures it.
 *
 *   node probe2.mjs [--network=studionet] [--address=0x…]
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
      const address = contractAddressOf(tx);
      console.log(`  probe at ${address}\n`);
      return address;
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
  const undetermined = out.status === "UNDETERMINED";
  console.log(`    ${undetermined ? "UNDETERMINED (validators disagreed)" : out.ok ? "COMMITTED (validators agreed)" : `FAILED ${out.status}`}  ${out.seconds ? out.seconds.toFixed(0) + "s" : ""}`);
  if (!out.ok && !undetermined) console.log(`    ${out.revertReason || out.stderr.slice(0, 300) || ""}`);
  let body = null;
  if (out.ok) { const raw = await report(); try { body = JSON.parse(raw); } catch { body = raw; } }
  findings[label] = { agreed: out.ok, undetermined, status: out.status, report: body };
  return findings[label];
}

// ------------------------------------------- 1. THE QUOTA, AS GITHUB SEES IT
// /rate_limit is exempt from the limit it reports, so it answers even while the
// bucket is empty. `remaining` on the consensus axis is the decisive test: one
// shared IP or one bucket per validator.
const rate = await experiment("rate_limit (remaining on the axis)", "probe_rate", ["https://api.github.com/rate_limit"]);
if (rate.report?.leader) {
  const L = rate.report.leader;
  const resetIn = L.reset ? Math.round(L.reset - Date.now() / 1000) : null;
  console.log(`    limit=${L.limit} remaining=${L.remaining} used=${L.used} reset in ${resetIn}s (${new Date(L.reset * 1000).toISOString()})`);
}
if (rate.undetermined) console.log(`    -> validators report DIFFERENT remaining: separate buckets`);
else if (rate.agreed) console.log(`    -> every validator reports the SAME remaining: ONE SHARED BUCKET`);

// -------------------------------------------------- 2. IS THE BUCKET EMPTY?
const still = await experiment("is the bucket still empty", "probe_statuses", [[
  "https://api.github.com/users/torvalds/repos?per_page=5&sort=updated",
  "https://api.github.com/repos/torvalds/linux/languages",
]]);
if (still.report) for (const [u, r] of Object.entries(still.report)) {
  console.log(`    ${String(r.status).padStart(4)} len=${String(r.len).padStart(6)}  ${u.slice(0, 66)}`);
  if (r.status !== 200) console.log(`         ${String(r.head).slice(0, 220).replace(/\n/g, " ")}`);
}

// -------------------------------------- 3. MIRRORS THAT DO NOT SHARE THE BUCKET
const mirrors = await experiment("keyless mirrors", "probe_statuses", [[
  "https://ungh.cc/users/torvalds/repos",
  "https://ungh.cc/repos/torvalds/linux",
  "https://api.codetabs.com/v1/proxy?quest=https://api.github.com/users/torvalds/repos",
]]);
if (mirrors.report) for (const [u, r] of Object.entries(mirrors.report)) {
  console.log(`    ${String(r.status).padStart(4)} len=${String(r.len).padStart(7)}  ${u.slice(0, 70)}`);
  console.log(`         ${String(r.head ?? r.err ?? "").slice(0, 200).replace(/\n/g, " ")}`);
}

// ------------------------------------------ 4. THE ONE-CALL LADDER ON THE AXIS
for (const [user, skill] of [["torvalds", "C"], ["gvanrossum", "Python"], ["kenil1710", "JavaScript"]]) {
  const f = await experiment(`onecall:${user}/${skill}`, "probe_level_onecall", [user, skill]);
  if (f.report?.leader) {
    const L = f.report.leader;
    console.log(`    level=${L.level} repos=${L.repo_count} own=${L.own_count} bytes=${L.total_bytes} listed=${L.listed} status=${L.status ?? 200}`);
    if (L.top) console.log(`    top=${JSON.stringify(L.top)}`);
  }
}

// -------------------------- 5. STRICT: MAY THE RECORD CARRY THE EVIDENCE TOO?
const strict = await experiment("onecall_strict:torvalds/C", "probe_onecall_strict", ["torvalds", "C"]);
if (strict.report?.leader) console.log(`    ${JSON.stringify(strict.report.leader)}`);

// ---------------------------------------------- 6. A USER WITH NOTHING TO SHOW
const none = await experiment("onecall:torvalds/Haskell (expect NONE)", "probe_level_onecall", ["torvalds", "Haskell"]);
if (none.report?.leader) console.log(`    ${JSON.stringify(none.report.leader)}`);

const missing = await experiment("onecall:nonexistent user", "probe_level_onecall", ["this-user-does-not-exist-skillverify-xyz", "Python"]);
if (missing.report?.leader) console.log(`    ${JSON.stringify(missing.report.leader)}`);

writeFileSync(new URL("../docs/probe2_findings.json", import.meta.url), JSON.stringify({ address, network: networkName, at: new Date().toISOString(), findings }, null, 2) + "\n");
console.log(`\n==> wrote docs/probe2_findings.json  (probe at ${address})`);
