/**
 * Verify a deployment that this session did not perform.
 *
 *   node check_deployment.mjs --network=bradbury \
 *        --oracle=0x… --consumer=0x…
 *
 * deploy.mjs runs these same checks immediately after it deploys, but a
 * deployment done from another machine — or in another session — has never been
 * checked by anything. Reading the addresses back is the difference between
 * "somebody told me these are live" and knowing it.
 *
 * READ-ONLY. It sends no transaction and needs no key, so it can be pointed at
 * any deployment by anyone.
 *
 * The load-bearing check is the last one. Two contracts can each exist and
 * answer perfectly while being wired to entirely different counterparties;
 * reading the oracle's config back THROUGH the consumer is the only cheap proof
 * that the pair is actually a pair.
 */
import { readFileSync } from "node:fs";
import { CHAINS, argOf, retry } from "./harness.mjs";
import { createClient } from "genlayer-js";

const networkName = argOf("network", "bradbury");
const chain = CHAINS[networkName];
if (!chain) throw new Error(`unknown network ${networkName}`);

let fallback = {};
try {
  fallback = JSON.parse(readFileSync(new URL("../deployments.json", import.meta.url), "utf8"))?.deployments?.[networkName] ?? {};
} catch { /* deployments.json is a convenience here, not a requirement */ }

const ORACLE = argOf("oracle", fallback.SkillVerify);
const CONSUMER = argOf("consumer", fallback.SkillConsumer);
if (!ORACLE || !CONSUMER) {
  throw new Error(`no addresses for ${networkName} — pass --oracle= and --consumer=`);
}

const read = createClient({ chain });
const view = (address, functionName, args = []) =>
  retry(() => read.readContract({ address, functionName, args }), { label: functionName });

const cfg = JSON.parse(await view(ORACLE, "get_config"));
const stats = JSON.parse(await view(ORACLE, "get_stats"));
const terms = JSON.parse(await view(CONSUMER, "get_terms"));
const viaConsumer = JSON.parse(await view(CONSUMER, "get_oracle_config"));

console.log(`SkillVerify    ${ORACLE}   (${networkName})`);
console.log(`  owner        ${cfg.owner}`);
console.log(`  paused       ${cfg.paused}   fee ${cfg.fee}`);
console.log(`  levels       ${JSON.stringify(cfg.levels)}`);
console.log(`  axis         ${JSON.stringify(cfg.axis_values)}`);
console.log(`  source       ${cfg.source}`);
console.log(`  bytes_basis  ${cfg.bytes_basis}   forks_counted ${cfg.forks_counted}`);
console.log(`  cooldown     ${cfg.cooldown_seconds}s   resolve_window ${cfg.resolve_window_seconds}s`);
console.log(`  verifications ${stats.total_verifications} — ${stats.resolved} resolved, ${stats.pending} pending, ${stats.stalled} stalled`);
console.log(`SkillConsumer  ${CONSUMER}`);
console.log(`  oracle       ${terms.oracle}`);
console.log(`  bounties     ${terms.bounties}   open_liability ${terms.open_liability}\n`);

const checks = [
  ["the oracle answers get_config", Array.isArray(cfg.levels) && cfg.levels.length === 4],
  ["four levels, lowest first", JSON.stringify(cfg.levels) === '["NONE","BEGINNER","PROFICIENT","EXPERT"]'],
  ["six axis values", JSON.stringify(cfg.axis_values) === '["EXPERT","PROFICIENT","BEGINNER","NONE","NO_SUCH_USER","UNAVAILABLE"]'],
  ["three statuses", JSON.stringify(cfg.statuses) === '["PENDING","RESOLVED","STALLED"]'],
  ["fee is 0", String(cfg.fee) === "0"],
  ["not paused", cfg.paused === false],
  ["forks are excluded", cfg.forks_counted === false],
  ["bytes basis is declared on chain", cfg.bytes_basis === "github_repo_size_kb"],
  ["the source is the search index, not the repo walk", String(cfg.source).includes("/search/repositories")],
  ["cooldown is 300s", Number(cfg.cooldown_seconds) === 300],
  ["EXPERT threshold is 5 repos", cfg.thresholds?.EXPERT?.repos === 5],
  ["views do not revert for an unknown id",
    JSON.parse(await view(ORACLE, "get_verification", [999999])).found === false],
  ["is_verified answers false rather than raising",
    (await view(ORACLE, "is_verified", ["nobody-at-all-here", "Cobol", "BEGINNER"])) === false],
  ["the consumer points at THIS oracle", String(terms.oracle).toLowerCase() === ORACLE.toLowerCase()],
  // The ladder is duplicated in the consumer so the oracle cannot silently
  // redefine what a bounty pays for. A mismatch must surface here, not at the
  // first claim.
  ["both ladders agree", JSON.stringify(terms.levels) === JSON.stringify(cfg.levels)],
  ["the consumer reads the oracle across the boundary",
    String(viaConsumer.owner ?? "").toLowerCase() === String(cfg.owner).toLowerCase()],
];

let bad = 0;
for (const [label, ok] of checks) {
  console.log(`  ${ok ? "ok  " : "FAIL"} ${label}`);
  if (!ok) bad++;
}
console.log(`\n  ${checks.length - bad}/${checks.length} checks passed`);
process.exit(bad ? 1 : 0);
