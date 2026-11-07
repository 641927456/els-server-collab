# Native cooldown commit observer repair

A real V108 dungeon session reached the native skip/commit common join without initialized pair/node storage. The statistics observer dereferenced that storage; the launcher misclassified the resulting script exception as a power-cache error and terminated its owned child in cleanup.

The four source changes arm a per-invocation marker only after the original insert/find returns, consume it once at the existing post-accumulation join, separate generic support errors from cache errors, and emit nested Python output as UTF-8. The fifth leaf updates required compatibility artifact hashes. Original computations, inserted/existing-key accumulation, owner/generation checks, economic rules, shared native sender support and all V109 housing changes are retained. No original game EXE/KOM, database, private configuration or server business code changes are included.

The exact V109 parent and candidate hashes are recorded in candidate-manifest.json. Root independently reviewed the author's patch, actual error trace, original control flow, lifecycle scope and pinned results; see independent-review.md. Successful same-input verification is reused: six added plus ten existing fixture groups, full composed-source/pin/error/UTF-8 checks, and actual Frida 17.23.3 native-host old-versus-fixed reproduction (four errors versus zero). Native host lookup/prologue/writer are explicit shims. Test sources reference private G: fixtures and are source records, not a redistributable game harness.

At this source commit, signing, actual dual-mode upgrade/load and natural gameplay acceptance are pending. Technical independent review is not GitHub approval. Retained roughly eight-hour online logs show no new post-V108 5BF or duplicate sequence, but do not prove their permanent absence. Historical 5BF payload and individual historical duplicate producers remain unconfirmed. The separate connection-queue performance issue is not changed here.

Only source and derived evidence are included; no credentials, player/account databases, raw packets or runtime logs are uploaded.
