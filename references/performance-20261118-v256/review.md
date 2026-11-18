# V256 server performance review

Reviewed ten frozen candidates (88–97), eleven effective runtime files, against installed V255. Reused each unchanged candidate test; composite checks cover dispatch and inventory interactions and four additive indexes.

Selected batch93 author-v2. Rejected its original prototype: it inverted FF26 world/mailbox lock ordering and let town reports enter the isolated dungeon path. The selected version preserves those original functions and routes town reports separately. Application finishes at batch96; dungeon_workers finishes at batch93-v2.

Changes reduce repeated inventory reads, add owner lookup indexes, separate existing-handler dispatch for selected town/dungeon calls, and add pickup timing stages. Identity, transaction, idempotency, full receipt contents and world-before-mailbox order remain intact. Composite complete protocol replies and SQLite results match parent cases. Four indexes are additive; recovery restores code only and preserves current data.

Scope limits: cartridge receipt counts are currently small; this is not evidence for the multi-second lag root cause. Potion routing affects only calls that reach Application fallback, not independent ConsumableLane waits. Diagnostic timings do not by themselves repair latency. Controlled party tests and synthetic SQL fixtures are not player/native GUI acceptance. Natural multiplayer swallowed damage and FPS remain open for post-install logs and player feedback.

No game EXE/KOM or client support changes, new test server, player account modification or database restore in this batch. Eleven server files, zero added runtime files, four nonunique indexes. Existing owned remote QA must be completely closed before maintenance. Installation uses actual advance server notices and one held publication transaction.
