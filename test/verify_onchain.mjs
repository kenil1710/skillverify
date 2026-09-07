/**
 * Reads every verification off the live contract and re-derives it.
 *
 *   node verify_onchain.mjs [--network=studionet] [--oracle=0x…]
 *
 * Independent of the E2E suite on purpose. The suite asserts as it goes; this
 * asks the chain what is actually stored, afterwards, and re-computes the level
 * from the counts the record itself carries. A record whose verdict does not
 * follow from its own evidence is the failure this is looking for.
 */
import { readFileSync } from "node:fs";
import { connect, argOf } from "./harness.mjs";

const networkName = argOf("network", "studionet");
const deployed = JSON.parse(readFileSync(new URL("./.deployed.json", import.meta.url), "utf8"));
const ORACLE = argOf("oracle", deployed.SkillVerify.address);
const c = connect({ networkName, address: ORACLE, role: "client" });

const RANK = { NONE: 0, BEGINNER: 1, PROFICIENT: 2, EXPERT: 3 };
const ladder = (repos, bytes) =>
  repos >= 5 && bytes >= 1000n ? "EXPERT"
  : repos >= 3 && bytes >= 500n ? "PROFICIENT"
  : repos >= 1 ? "BEGINNER" : "NONE";

const stats = await c.viewJson("get_stats");
const cfg = await c.viewJson("get_config");
console.log(`SkillVerify @ ${ORACLE}  (${networkName})`);
console.log(`  ${stats.total_verifications} verifications — ${stats.resolved} resolved, ${stats.pending} pending, ${stats.stalled} stalled`);
console.log(`  ${stats.users_verified} users, ${stats.skills_verified} skills, ${stats.pairs_verified} pairs`);
console.log(`  source: ${cfg.source}`);
console.log(`  bytes_basis: ${cfg.bytes_basis}   forks_counted: ${cfg.forks_counted}\n`);

console.log("  id  status    level       repos  index  bytes            hash              user / skill");
console.log("  " + "─".repeat(104));

let bad = 0, resolved = 0;
for (let id = 1; id < Number(stats.next_id); id++) {
  const r = await c.viewJson("get_verification", [id]);
  if (!r.found) continue;
  const bytes = BigInt(r.total_bytes);
  const expect = ladder(r.repo_count, bytes);
  const levelOk = r.status !== "RESOLVED" || r.level === expect;
  const rankOk = r.level === "" || r.level_rank === RANK[r.level];
  const hashOk = r.status !== "RESOLVED" ? r.content_hash === "" : r.content_hash.length === 16;
  if (r.status === "RESOLVED") resolved++;
  if (!levelOk || !rankOk || !hashOk) bad++;
  const flag = levelOk && rankOk && hashOk ? " " : "!";
  console.log(`  ${flag}${String(id).padStart(3)} ${r.status.padEnd(9)} ${(r.level || "—").padEnd(11)} ${String(r.repo_count).padStart(5)} ${String(r.index_count).padStart(6)}  ${String(r.total_bytes).padStart(14)}  ${(r.content_hash || "—").padEnd(16)}  ${r.github_username} / ${r.skill}`);
  if (!levelOk) console.log(`       ^ LEVEL MISMATCH: stored ${r.level}, evidence gives ${expect}`);
  if (!rankOk) console.log(`       ^ RANK MISMATCH: ${r.level_rank} for ${r.level}`);
  if (!hashOk) console.log(`       ^ HASH: ${r.status} carries "${r.content_hash}"`);
  if (r.top_repos?.length) console.log(`       top: ${r.top_repos.join(", ")}`);
}

console.log("\n  " + "─".repeat(104));
// The headline claims, checked against what is actually on chain.
const CLAIMS = [
  ["torvalds", "c", "EXPERT"],
  ["gvanrossum", "python", "EXPERT"],
  ["kenil1710", "javascript", "EXPERT"],
  ["torvalds", "haskell", "NONE"],
  ["torvalds", "notalanguage", "NONE"],
  ["nlohmann", "c++", "EXPERT"],
  ["microsoft", "c#", "EXPERT"],
];
console.log("\n  headline claims, read back off chain:");
for (const [user, skill, expected] of CLAIMS) {
  const row = await c.viewJson("get_latest", [user, skill]);
  if (!row.found) { console.log(`    ..   ${user}/${skill} — never resolved on this deployment`); continue; }
  const ok = row.level === expected;
  if (!ok) bad++;
  console.log(`    ${ok ? "ok  " : "FAIL"} ${user}/${skill} is ${row.level} (${row.repo_count} repos, index said ${row.index_count})`);
}

console.log(`\n  ${resolved} resolved records re-derived, ${bad} inconsistent.`);
process.exit(bad ? 1 : 0);
