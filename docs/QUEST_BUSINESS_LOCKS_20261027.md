# Quest fixtures, no-work business previews and SQLite waits

Issue #578. This work continues the actually accepted PR #577 runtime and
waits behind the previously handed-off Mod360 publication (PR #576). The final
binding must use both actual formal parents after that batch is accepted and
cleaned up; no Git checkout replaces either whole runtime.

## Legacy fixture diagnosis

The two reported failures stopped in `first_completed()` for ordinary quest6980.
The shared F4 builder set flags `(0,1,1,1,0)`. The current wire contract defines
flags[1] as Epic skip; `epic_skip.reward` correctly rejects this non-Epic quest
with2005 (`0x7d5`). Ordinary claims use `(0,0,1,1,0)`. Both original tests then
pass: death-proof deduplication/conflict/cold restore, and full-bag/serialization
rollback/retry without duplicate reward. A regression keeps the original wrong
flag rejected and verifies the entire save stays unchanged before a valid claim.
No production quest/skip/source/actor qualification is relaxed.

Additional fixture contracts exposed by the corrected shared helper are explicit:
expiration of one timed stack containing three collection items removes all3,
while a partial discard of one item still leaves2; an unqualified synthetic
`retire` event is rejected without fabricated progress; the historical dungeon
trace is a private asset outside this locked engine and its dependent case has
an explicit dependency skip. This does not accept a natural positive retirement
or dungeon-controller path. The old root reward-module shim is replaced with the
official storage import and the original transaction assertions are discoverable
as a unittest case. Original failures and exception traces remain private evidence.

## Runtime delta

Twelve existing engine leaves, no new resource, runtime module, table, installation
DDL, client modification, or player database restoration:

* Tutorial restoration first opens a consistent, owner-qualified read snapshot.
  Only complete old schemas, existing story state, and absence of any potentially
  missing admitted After edge can exclude a writer. Missing schema, possible
  starter, or any possible deferred edge repeats the entire original writer
  path, including current SQL, source/capacity/abandon checks and precommit reply
  encoding. No preview authorizes a write or fabricates task progress.
* Idle expiry and legacy circuit checks use the existing operation-local
  read-only connection. A positive preview closes its read snapshot, acquires
  the same original writer, and rereads exact deadlines/items/options. Existing
  expiry comparison and permanent migration receipts stay unchanged.
* Pure quest/activity readers reuse a scoped read-only connection, preserving
  read-transaction boundaries and live guards. No authority or cross-request
  economic value is cached.
* Registration, inventory split/discard/initialization, circuit and growth
  recovery writers gain the existing wait/BUSY/scope-duration observation.
  Manual reward grants observe their own BEGIN/commit/rollback lifetime without
  acquiring, committing, closing or double-counting a caller's shared writer.
  All original connections,10-second timeouts, savepoints, receipts and precommit
  encoding remain. Scope duration can exceed actual held time after an explicit
  early commit/rollback; it is not an exact single-lock measurement.

`tools/verify_quest_business.py --with-runtime --assets-root <locked-runtime>`
materializes both pinned channels and exercises the retained regressions plus
the repaired quest fixtures, inventory/reward transactions and12 new boundary
cases. These cover no-work reads under another reserved writer, foreign owners,
missing lazy tables, changes between preview and writer, encoding rollback,
shared-writer ownership, BUSY propagation and once-only economic retry.

Controlled five-create/ten-role reply hashes match. Limited same-machine warm
handler medians were selection68.62→55.73ms and town65.50→56.47ms. They are
diagnostic samples, not natural GUI/WAN RTT or multiplayer peak P95. The final
private receipts record actual parent preservation, source checks, protected
dual deployment, public first/cold QA, observation and owned resource cleanup.
Unobserved SQLite writers and real business projections can still cause delays;
this change does not add concurrent writers, shorten timeouts or claim every
possible stall has disappeared.
