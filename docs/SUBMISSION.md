SkillVerify — a developer skill verification oracle.

"Does GitHub user U write language L?" Validators independently query GitHub's index and agree on EXPERT/PROFICIENT/BEGINNER/NONE. SkillConsumer gates a bounty on it.

FIXED: the compared axis was the level alone, but the stored level was recomputed from the leader's repo_count/total_bytes, which nothing compared. A leader could report NONE, have validators agree, attach repo_count=100, and land EXPERT. The key now binds level+counts, and _apply refuses any level the agreed counts contradict; stored values are the agreed ones. Cost: a repo pushed mid-round lands UNDETERMINED, which writes nothing and is retried.

Probing changed the design 3x: one shared 60/hr IP; an unknown `language:` 200s with everything; `language:C++` returns C.

Studio Dev, 18/18 read-only checks — oracle 0x4a5db424A4bF1b839081aFFD6a4a2cC3a8C4614f

369 offline tests · 22 AST checks, mutation-tested.
github.com/kenil1710/skillverify
