/**
 * Probe round 4 — the encoding question, and it is not cosmetic.
 *
 * The contract builds `q=user:{U}+language:{L}`. In a query string `+` IS a
 * space and `#` starts a fragment, so `language:C++` and `language:C#` are two
 * of the most-claimed skills in existence and both may reach GitHub as
 * something else entirely. Round 3 proved GitHub silently ignores a language
 * qualifier it cannot parse and returns the user's whole repo list, so the
 * failure mode here is not an error — it is a confident wrong answer.
 *
 * Each row is one search request and the bucket is 10/minute, so the runner
 * paces itself.
 */
import { createClient, createAccount } from "genlayer-js";
import { readFileSync, writeFileSync } from "node:fs";
import { CHAINS, accounts, argOf, contractAddressOf, fundOnStudio, outcomeOf, retry, sleep } from "./harness.mjs";

const networkName = argOf("network", "studionet");
const chain = CHAINS[networkName];
const acc = accounts();
const account = createAccount(acc.client.key);
const wallet = createClient({ chain, account });
const read = createClient({ chain });
const findings = {};

async function deployProbe() {
  const reuse = argOf("address", null);
  if (reuse) { console.log(`==> reusing probe at ${reuse}`); return reuse; }
  await fundOnStudio(chain, account.address, 100n * 10n ** 18n);
  const code = readFileSync(new URL("../contracts/_render_probe.py", import.meta.url));
  console.log(`==> deploying probe (${code.length} bytes)`);
  const hash = await retry(() => wallet.deployContract({ code, args: [] }), { label: "deploy" });
  const started = Date.now();
  for (;;) {
    const tx = await retry(() => read.getTransaction({ hash }), { attempts: 4, label: "poll" }).catch(() => null);
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

const BASE = "https://api.github.com/search/repositories?per_page=100&sort=updated&q=";
// label, query as it goes on the wire, what a correct answer looks like
const CASES = [
  ["C++ via literal +",        "user:torvalds+language:C++",              "the naive spelling — + is a space"],
  ["C++ via %2B%2B, + sep",    "user:torvalds+language:C%2B%2B",          "encoded value, + as separator"],
  ["C++ via %2B%2B, %20 sep",  "user:torvalds%20language:C%2B%2B",        "both encoded — the candidate"],
  ["C via %20 sep",            "user:torvalds%20language:C",              "control: %20 must still work"],
  ["C# on a user who has it",  "user:microsoft%20language:C%23",          "# must be %23 or the URL is truncated"],
  ["C# via literal #",         "user:microsoft%20language:C#",            "the naive spelling — # starts a fragment"],
  ["multi-word, quoted",       "user:jakevdp%20language:%22Jupyter%20Notebook%22", "space inside a value needs quotes"],
  ["multi-word, unquoted",     "user:jakevdp%20language:Jupyter%20Notebook",       "unquoted — second word becomes a term"],
  ["Objective-C hyphen",       "user:AFNetworking%20language:Objective-C", "a hyphen needs no encoding"],
];

let n = 0;
for (const [label, q, why] of CASES) {
  // 10 searches/minute, shared across every validator in the round.
  if (n++ > 0) { console.log("    (pacing 20s for the search bucket)"); await sleep(20_000); }
  process.stdout.write(`==> ${label}\n    ${why}\n    q=${q}\n`);
  const out = await send("probe_raw_search", [BASE + q]);
  const und = out.status === "UNDETERMINED";
  console.log(`    ${und ? "UNDETERMINED" : out.ok ? "COMMITTED" : `FAILED ${out.status}`}`);
  let body = null;
  if (out.ok) { const raw = await report(); try { body = JSON.parse(raw); } catch { body = raw; } }
  if (body) {
    console.log(`    status=${body.status} total_count=${body.total_count} returned=${body.returned}`);
    console.log(`    languages=${JSON.stringify(body.languages)}`);
    if (body.head) console.log(`    head=${String(body.head).slice(0, 200)}`);
  }
  findings[label] = { q, why, report: body, status: out.status };
}

writeFileSync(new URL("../docs/probe4_findings.json", import.meta.url), JSON.stringify({ address, at: new Date().toISOString(), findings }, null, 2) + "\n");
console.log(`\n==> wrote docs/probe4_findings.json`);
