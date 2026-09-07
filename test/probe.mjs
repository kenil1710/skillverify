/**
 * Deploys contracts/_render_probe.py and runs every experiment behind
 * docs/PROBE.md.  node probe.mjs [--network=studionet] [--address=0x…]
 *
 * The probe is a THROWAWAY. It is deployed, interrogated and abandoned; nothing
 * in SkillVerify imports it. What survives is docs/PROBE.md and the design
 * decisions it forces.
 *
 * Reading a drift experiment needs care, and it is why this is a script rather
 * than a handful of CLI calls:
 *
 *   A transaction that lands UNDETERMINED is not a failure of the probe. It is
 *   the ANSWER — validators re-fetched and disagreed. So `undetermined` is
 *   reported as a first-class outcome next to `ok`, and never as an error.
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

const GH = "https://api.github.com";
const REPOS_5 = `${GH}/users/torvalds/repos?per_page=5&sort=updated`;
const LANGS = `${GH}/repos/torvalds/linux/languages`;
const REPOS_100 = `${GH}/users/torvalds/repos?per_page=100&sort=updated`;

const findings = {};

async function deployProbe() {
  const reuse = argOf("address", null);
  if (reuse) {
    console.log(`==> reusing probe at ${reuse}`);
    return reuse;
  }
  await fundOnStudio(chain, account.address, 100n * 10n ** 18n);
  const code = readFileSync(SRC);
  console.log(`==> deploying probe (${code.length} bytes) as ${account.address}`);
  const hash = await retry(() => wallet.deployContract({ code, args: [] }), { label: "deploy" });
  const started = Date.now();
  for (;;) {
    const tx = await retry(() => read.getTransaction({ hash }), { attempts: 4, label: "deploy poll" }).catch(() => null);
    const out = outcomeOf(tx);
    if (out.settled) {
      if (!out.ok) throw new Error(`probe deploy failed: ${out.revertReason || out.stderr.slice(0, 500)}`);
      const address = contractAddressOf(tx);
      console.log(`  probe at ${address} (${((Date.now() - started) / 1000).toFixed(0)}s)\n`);
      return address;
    }
    if (Date.now() - started > 300_000) throw new Error("probe deploy never settled");
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
  const verdict = undetermined ? "UNDETERMINED (validators disagreed)" : out.ok ? "COMMITTED (validators agreed)" : `FAILED ${out.status}`;
  console.log(`    ${verdict}  ${out.seconds ? out.seconds.toFixed(0) + "s" : ""}`);
  if (!out.ok && !undetermined) console.log(`    ${out.revertReason || out.stderr.slice(0, 300) || ""}`);
  let body = null;
  if (out.ok) {
    const raw = await report();
    try { body = JSON.parse(raw); } catch { body = raw; }
  }
  findings[label] = { agreed: out.ok, undetermined, status: out.status, report: body };
  return findings[label];
}

// ---------------------------------------------------------------- 1. EGRESS
const statuses = await experiment("egress", "probe_statuses", [[
  REPOS_5,
  LANGS,
  REPOS_100,
  // A user that does not exist: a deterministic 404 every node agrees on. It
  // must be distinguishable from a rate limit, because one is a permanent
  // "no such user" and the other must never be read as "this user has no repos".
  `${GH}/users/this-user-does-not-exist-skillverify-xyz/repos?per_page=5`,
  // A real user with zero public repos would answer 200 with `[]`. Closest
  // stable stand-in: a repo whose languages map is empty.
  `${GH}/repos/octocat/Spoon-Knife/languages`,
]]);
if (statuses.report) {
  for (const [u, r] of Object.entries(statuses.report)) {
    console.log(`    ${String(r.status).padStart(4)}  len=${String(r.len).padStart(7)}  ${u.slice(0, 74)}`);
    if (r.head) console.log(`          ${String(r.head).slice(0, 200).replace(/\n/g, " ")}`);
    if (r.err) console.log(`          ERR ${r.err}`);
  }
}

// ----------------------------------------------------------------- 2. SHAPE
const shapeRepos = await experiment("shape:repos", "probe_shape", [REPOS_5, 2]);
if (shapeRepos.report) console.log("    " + JSON.stringify(shapeRepos.report).slice(0, 1800));

const shapeLangs = await experiment("shape:languages", "probe_shape", [LANGS, 2]);
if (shapeLangs.report) console.log("    " + JSON.stringify(shapeLangs.report).slice(0, 1200));

// ------------------------------------------------------- 3. REPO LIST SHAPE
const repos = await experiment("repos:torvalds", "probe_repos", ["torvalds", 100]);
if (repos.report) {
  const r = repos.report;
  console.log(`    count=${r.count} forks=${r.forks} null_lang=${r.null_lang} status=${r.status} len=${r.len}`);
  for (const x of (r.repos ?? []).slice(0, 12)) {
    console.log(`      ${x.fork ? "FORK" : "own "}  ${String(x.lang).padEnd(14)} ${x.name}`);
  }
}

// ----------------------------------------------------------------- 4. DRIFT
await experiment("drift:repos", "probe_drift", [REPOS_5]).then((f) => {
  if (f.report) console.log(`    leader len=${f.report.leader?.len} status=${f.report.leader?.status}`);
});
await experiment("drift:languages", "probe_drift", [LANGS]).then((f) => {
  if (f.report) console.log(`    body: ${String(f.report.leader?.body ?? "").slice(0, 300)}`);
});

// --------------------------------------------- 5. THE LEVEL ON THE AXIS
for (const [user, skill, cap] of [
  ["torvalds", "C", 10],
  ["gvanrossum", "Python", 10],
  ["kenil1710", "JavaScript", 10],
]) {
  const f = await experiment(`level:${user}/${skill}`, "probe_level", [user, skill, cap]);
  if (f.report?.leader) {
    const L = f.report.leader;
    console.log(`    level=${L.level} repos=${L.repo_count} bytes=${L.total_bytes} scanned=${L.scanned} calls=${L.calls} errors=${L.errors}`);
    console.log(`    top=${JSON.stringify(L.top)}`);
  }
}

// --------------------------- 6. STRICT: THE WHOLE RESULT ON THE AXIS
const strict = await experiment("level_strict:torvalds/C", "probe_level_strict", ["torvalds", "C", 10]);
if (strict.report?.leader) console.log(`    ${JSON.stringify(strict.report.leader)}`);

// ------------------------------------------------------ 7. REQUEST BUDGET
const budget = await experiment("budget:torvalds x25", "probe_budget", ["torvalds", 25]);
if (budget.report) {
  const b = budget.report;
  console.log(`    list_status=${b.list_status} calls=${b.n} first_bad=${b.first_bad}`);
  const bad = (b.seq ?? []).filter((s) => s.status !== undefined && s.status !== 200);
  console.log(`    non-200: ${bad.length}  ${JSON.stringify(bad.slice(0, 6))}`);
  const head = (b.seq ?? []).find((s) => s.head);
  if (head) console.log(`    first bad body: ${String(head.head).slice(0, 240)}`);
}

writeFileSync(new URL("../docs/probe_findings.json", import.meta.url), JSON.stringify({ address, network: networkName, at: new Date().toISOString(), findings }, null, 2) + "\n");
console.log(`\n==> wrote docs/probe_findings.json  (probe at ${address})`);
