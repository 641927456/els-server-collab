# Static preparation and cancelled-periodic review

Self-review using differential-review, against SHA-pinned installed native-dungeon-startup-prewarm-20261104-v1. Three existing server files change. This record is not a GitHub approval.

## Result and scope

- Application.start adds 40 previously audited static loader/import invocations, the immutable native dungeon-type map, and the existing HP classification/factor caches for 276 finite policy IDs. The earlier eight loaders remain in place. All run before LocalAccount construction/listeners. Player data, drops, cooldowns, activity clocks and economic transactions are not precomputed.
- title_economy builds a read-only map for all 740 actual native dungeon definitions in one catalog pass. The pinned Enum is parsed and verified once instead of once for each newly visited map. Every mode retains the original integer/range validation; a missing native ID still raises ValueError. Virtual HP graph40046 is not synthesized as a native row.
- periodic_work publishes the routing snapshot only if at least one member actually executed. An all-cancelled slice has changed no worker state and no longer performs registry/manifest work while holding world admission. The executed member/error paths still publish; started members remain indivisible.

## Queue investigation

The prior public timing recorded 92.11ms before executor admission, but did not record the holder. Isolated profiling found real periodic work can take48ms locally; that alone cannot establish attribution to the historical event. A more specific reproducible race exists: foreground cancels a pending periodic claim after the batch has entered world admission; the cancelled batch still invokes routing publication in its finally block. No periodic member timing is recorded because no member ran.

The deterministic reproducer uses actual WorldGate, BoundedBusinessQueue, PeriodicClaim, periodic_chunks and PeriodicScheduler.foreground. Only the owned test publisher is held for92ms to represent a slow snapshot. Baseline foreground waiting93.19ms with one needless publication; candidate0.33ms with zero publications. This demonstrates and fixes that blocking path, not retrospective proof of which task occupied the original production interval.

## Invariants and coverage

Mixed cancelled/executed batches preserve results and order. A started member rejects cancellation and completes once; an executed failing member retains its exception and publishes before releasing the gate. Priority, fairness, bounded admission, transaction cancellation rules and scheduler ownership are unchanged.

Skipping the empty publication creates no authorization bypass: no member state changed, foreground operations retain their normal publication, and independent realtime registry/session invalidation remains in place. Existing account/lease guards, rewards, receipts and source qualification consumers are untouched.

The blast radius is one startup branch, one pure dungeon-type lookup used by title economy, and one periodic slice function shared by up to16 members. Pinned Git archive history from076874133bf70d4b039876f8f15f2f21af6212df/PR831 was checked for the preceding startup change; installed periodic_work/title economy bytes provide the exact baseline where main's active code is older. No security check was removed.

Actual candidate startup verified40 cache/import entries before player-store construction; all740 type values equal the original native definitions and all lookups complete without opening the catalog again. The immutable map rejects mutation; unknown virtual ID rejects; injected static catalog failure occurs before either player DB is created. Genuine source-qualified owned TLS pickups and cold balances are verified separately. Owned runtimes are removed.

No actionable correctness/security issue found. ONLINE publication still requires the existing backup, orderly maintenance, actual file verification, observation, public QA and exact cleanup. Natural GUI combat and production load testing are not claimed.
