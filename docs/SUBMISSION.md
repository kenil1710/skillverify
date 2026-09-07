SkillVerify — a developer skill verification oracle.

"Does GitHub user U write language L?" Validators independently query GitHub's search index and agree on one string: EXPERT/PROFICIENT/BEGINNER/NONE. Any contract can gate on it — SkillConsumer is a bounty only verified devs claim.

Probing changed the design 3x:

• The planned per-repo /languages walk 403'd after one verification: 60/60 used against ONE IP shared by all validators — cost is calls×validators, 1/hour network-wide. Now search/repositories: 1 request, own bucket.
• GitHub silently ignores an unknown `language:` qualifier, returning 200 with everything: "Notalanguage" scored EXPERT. Fixed by re-checking each item's language — on chain, repos=0 index=9.
• `language:C++` returns repos tagged C. C# too. Both 200. Fixed by encoding+quoting.

350 offline tests · 17 AST checks, mutation-tested · 111 live assertions, 0 failed.
github.com/kenil1710/skillverify · 0xA89c18414E586741b91e057213ca3007A6E06cCf
