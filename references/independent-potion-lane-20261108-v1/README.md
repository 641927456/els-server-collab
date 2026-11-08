# Independent potion processing for ordinary solo dungeons

Authenticated potion requests previously waited behind every queued monster settlement. This change gives loaded ordinary solo dungeon medicine its own bounded queue and four-worker pool, while retaining the existing authenticated connection, native packets, ownership checks and atomic count/cooldown/receipt transaction. Original EXE/KOM and client support files are unchanged.

Nine exact runtime leaves are archived against the accepted V110 parent, whose manifest and leaf SHA values are in candidate.json. Canonical root source is older than that parent; this archive preserves deployed source without overwriting unrelated root work. Existing successful ERP 610 replaces duplicate full-role D9 and reuses immutable page state with original revision/level/period boundaries.

Scene changes drain admitted medicine first; disconnect waits for actual worker retirement. Full-level medicine can overlap settlement. Below level 99, a read-only worker checks level, then medicine waits only for the current native reply and runs ahead of remaining deaths, preserving level-up and potion effect ordering. Parties, shared/special rooms and challenge-timed runs retain their existing path. SQLite writes still serialize.

Same-input isolated TLS verification: six deaths plus full recovery potion improved from 397.408 ms to 33.887 ms, with equal XP, six kill receipts, one medicine receipt and one debit. Seven boundary cases cover 24 queued deaths behind a blocked worker, scene invalidation during SQL writer wait, exit ordering, automatic pet medicine/CD, disconnect retirement, final authority rollback and level 98-to-99 AF-before-medicine-before-next-death. All owned temporary runtime/connection resources were removed. ERP byte comparisons and original native 610 consumer replay are reused for the unchanged two ERP leaves.

security-review.md is the author's differential self-review, not an independent reviewer or GitHub approval. Test sources reference private G: resources and are source records rather than a portable game harness. No credentials, databases, raw packets or runtime logs are included. At this source commit, merge, signed delivery and online/local installation are pending. Natural GUI, full battle, shared-mode parallel medicine and production latency are not qualified by isolated results.

Fixes #960.
