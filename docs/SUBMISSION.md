SkillVerify — a developer skill verification oracle.

"Does GitHub user U write language L?" Validators independently query GitHub's search index and agree on EXPERT/PROFICIENT/BEGINNER/NONE. SkillConsumer gates a bounty on it.

FIXED: the compared axis was the level alone, while the stored level was recomputed from the leader's repo_count/total_bytes, which nothing compared. A leader could report NONE, have validators agree, attach repo_count=100, and land EXPERT. The key now binds level+counts, and _apply refuses any level the agreed counts contradict. Stored values are the agreed ones. Cost: a repo pushed mid-round lands UNDETERMINED, which writes nothing and is retried; a RESOLVED record is frozen.

Probing changed the design 3x: validators share a 60/hr IP, killing the per-repo walk; an unknown `language:` 200s with everything; `language:C++` returns C.

369 offline tests · 22 AST checks, mutation-tested · 111 live assertions.
github.com/kenil1710/skillverify
