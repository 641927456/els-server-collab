# Selection/town business reads and SQLite boundaries

Issue #575. Parent: the actually accepted `server-character-slow-paths-20261027-v1`
and its LOCAL counterpart, reconstructed by the existing pinned channel profile.
PR #574 and its architecture ancestors are deployment dependencies; pending Git
review is recorded separately from the already accepted runtime.

The previous controlled sample still spent about 82ms in warm selection and
71ms in warm scene-ready handling. Repeated component connections and quest
notification snapshots contributed to those calls. Career recovery also reserved
the SQLite writer before discovering an ineligible role; a black-market projection
reserved a writer despite having no request or SQL mutation.

This candidate changes 18 existing engine leaves, with no resource/client delta,
new table, new runtime module, installation DDL, or database restoration:

* Ineligible paid-career recovery returns from a read-only, owner-qualified
  snapshot. Eligible candidates still acquire the original writer and repeat all
  ownership, character, paid provenance, consumption and precommit encoding checks.
* Black-market projections with no request use an explicit query-only read
  transaction. Real requests and application deadline settlements keep the
  original writer. Complete live actor guards, encoding, snapshot consistency and
  publication after transaction exit remain in both branches.
* Enumerated pure character/bank/wardrobe/guild/cash/location/skills/growth readers
  reuse the previous operation-local read-only connection. No authority value,
  economic reply or cross-request role is cached. Nested transactions keep their
  independent disposable reader; every exit ends the read transaction.
* Reply-only quest notifications may be reused inside one operation. Account,
  UID, file identity, SQLite `data_version` and the wall-second boundary invalidate
  the value. Results are copied; mutating quest and lease checks retain live reads.
* The existing SHA-checked skill-trait catalog is prepared before listening or
  opening character writers. Validation remains enabled.
* Existing writer instrumentation now also covers recovery, expiration, fishing
  login, growth, attendance, fatigue, tutorial/quest and market transactions. The
  ordinary sqlite3 connection, 10-second connection timeout, BEGIN IMMEDIATE,
  commit/rollback and single business writer are preserved. Explicit caller
  rollback and every uninstrumented SQL path are not implied to be measured.

`python -B tools/verify_selection_business.py` checks the pinned source and exact
delta against its parent. `--with-runtime --assets-root <locked-formal-runtime>`
materializes each channel in an owned temporary view and runs the retained
regressions plus the new lock/owner/cache/rollback and real App/TLS projection
tests. Git source CI and actual runtime regression results must be reported
separately; the repository's runtime Actions job remains main-only.

Controlled before/after native reply hashes match for five creates and ten role
reads. A limited sample measured warm handler medians selection 81.53→62.53ms
and town 70.82→63.75ms. These are diagnostic samples, not player network RTT,
GUI acceptance or peak multiplayer P95. Actual deployment, observations, precise
QA-account cleanup and source preservation are recorded in the private delivery
receipts after normal protected publication. Other SQLite writers, expensive
business decoding, synchronous critical logging fallback, disk and network
pressure remain possible latency sources.

Accepted dual delivery: `server-selection-town-business-20261027-v1` and LOCAL, 121.81/123.97s observation, full1242/1264 business and1718 LOCAL runtime hashes, first/cold protocol reads,256 auxiliary requests and exact owned-authentication/capacity cleanup. Both owned locks/tasks/stage have been released; this queue priority has ended.

176 targeted cases:171 passed and5 channel skips; four additional expiration checks passed. Two supplementary legacy full-quest fixtures fail identically on the accepted unmodified parent before their target scenarios (0x7d5); original failures are retained and no guards were relaxed. Per-request SQL writer duration covers the transaction scope; an explicit early rollback can make it overestimate actual lock hold time.
