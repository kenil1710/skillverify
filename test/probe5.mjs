/**
 * Probe round 5 — does the quoting rule hold for SINGLE words too?
 *
 * Round 4 settled that the language value must be percent-encoded (C++ and C#
 * are otherwise read as C, silently) and that a multi-word value must be
 * QUOTED (`"Jupyter Notebook"` gives 31 repos, unquoted gives 7 — the second
 * word becomes a free-text term). That leaves one question, and the contract's
 * URL builder cannot be written without the answer: is a quoted value safe for
 * ORDINARY single-word languages, so one code path serves both, or must the
 * quotes be conditional on a space?
 */
import { createClient, createAccount } from "genlayer-js";
import { readFileSync, writeFileSync } from "node:fs";
import { CHAINS, accounts, argOf, contractAddressOf, fundOnStudio, outcomeOf, retry, sleep } from "./harness.mjs";

const chain = CHAINS[argOf("network", "studionet")];
const acc = accounts();
const account = createAccount(acc.client.key);
const wallet = createClient({ chain, account });
const read = createClient({ chain });
const findings = {};

const reuse = argOf("address", null);
let address = reuse;
if (!address) {
  await fundOnStudio(chain, account.address, 100n * 10n ** 18n);
  const code = readFileSync(new URL("../contracts/_render_probe.py", import.meta.url));
  const hash = await retry(() => wallet.deployContract({ code, args: [] }), { label: "deploy" });
  const started = Date.now();
  for (;;) {
    const tx = await retry(() => read.getTransaction({ hash }), { attempts: 4, label: "poll" }).catch(() => null);
    const out = outcomeOf(tx);
    if (out.settled) { if (!out.ok) throw new Error("deploy failed"); address = contractAddressOf(tx); break; }
    if (Date.now() - started > 300_000) throw new Error("never settled");
    await sleep(1500);
  }
}
console.log(`==> probe at ${address}\n`);

async function send(functionName, args) {
  const hash = await retry(() => wallet.writeContract({ address, functionName, args, value: 0n }), { label: functionName });
  const started = Date.now();
  for (;;) {
    const tx = await retry(() => read.getTransaction({ hash }), { attempts: 4, label: "poll" }).catch(() => null);
    const out = outcomeOf(tx);
    if (out.settled) return out;
    if (Date.now() - started > 400_000) return { ...outcomeOf(null), status: "UNSETTLED" };
    await sleep(1500);
  }
}
const report = async () => retry(() => read.readContract({ address, functionName: "get_report", args: [] }), { label: "get_report" });

const BASE = "https://api.github.com/search/repositories?per_page=100&sort=updated&q=";
const CASES = [
  ["quoted single word",   `user:torvalds%20language:%22C%22`,        `must match the 8 that bare language:C gave`],
  ["quoted C++, real owner", `user:nlohmann%20language:%22C%2B%2B%22`, `a user who genuinely owns C++ repos, not forks`],
  ["bare C++, real owner",   `user:nlohmann%20language:C++`,           `the trap, on a user where the right answer is nonzero`],
  ["quoted nonsense lang",   `user:torvalds%20language:%22Notalanguage%22`, `the silent-ignore bug must still be caught by the item filter`],
  ["username with a dash",   `user:kenil1710%20language:%22TypeScript%22`,  `real account, hyphenless control for the E2E`],
];

let n = 0;
for (const [label, q, why] of CASES) {
  if (n++ > 0) { console.log("    (pacing 20s — 10 searches/minute)"); await sleep(20_000); }
  process.stdout.write(`==> ${label}\n    ${why}\n    q=${q}\n`);
  const out = await send("probe_raw_search", [BASE + q]);
  console.log(`    ${out.status === "UNDETERMINED" ? "UNDETERMINED" : out.ok ? "COMMITTED" : `FAILED ${out.status}`}`);
  let body = null;
  if (out.ok) { const raw = await report(); try { body = JSON.parse(raw); } catch { body = raw; } }
  if (body) {
    console.log(`    status=${body.status} total_count=${body.total_count} returned=${body.returned} languages=${JSON.stringify(body.languages)}`);
    if (body.head) console.log(`    head=${String(body.head).slice(0, 220)}`);
  }
  findings[label] = { q, why, report: body, status: out.status };
}

writeFileSync(new URL("../docs/probe5_findings.json", import.meta.url), JSON.stringify({ address, at: new Date().toISOString(), findings }, null, 2) + "\n");
console.log(`\n==> wrote docs/probe5_findings.json`);
