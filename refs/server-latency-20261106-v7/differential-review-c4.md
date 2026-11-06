# C4 differential self-review

Implementing-agent review, 2026-11-06. This is not independent approval or a production latency qualification. Cloud capacity testing is pending at this review revision.

## Source and history

Seven leaves apply to the accepted `native-player-feedback-repairs-20261106-v1` parent, manifest `f60e41011b442851d8f36e4785d52cd0d0eb7c4f5e61040aee053df28e17b7fc`. The ten feedback repairs remain in the parent. `review-bindings-c4.json` records exact before/after hashes, line deltas and the matching Git parent archive for every leaf, on main `e2cc9a58021a31c515a2efdf5f449250ab5e22f0`. Six matching originals are in the unified-latency archive; the inventory original is in the player-feedback Kobo choice archive. Git blame attributes the attendance baseline to #889; the potion-choice rule was integrated by #906. Installed source identity is checked separately from Git history.

The existing C3 review covers the unchanged death/coin writer and clock changes. Their late-ready jobs retain the sixteen-job bound, original savepoints, physical FULL commit before futures, replay/source/owner validation and normal close. No world queue is added. The final-parent writer tests, actual capped solo gate and two-member party/dead-guest/revive tests passed again against C4's complete dependency set.

## Attendance preparation boundary (high risk)

`AttendanceAwardFlow._projection` has one direct production caller, `finalize`. Its selected factory constructs `AttendanceAwards`, whose carry-policy `_refresh` overrides the base task calculation. Both implementations now accept `persist=False`; default callers in accept, snapshot and claim retain synchronous persistence. `_write_refresh` has three direct call sites: those two calculators and the projection writer. `_refresh_signature` is used twice by that projection. No economic amount, schedule, reward pool, receipt, mail or protocol schema is changed.

The original fact scan, checksum verification, period/timestamp validation and union of observed online intervals run inside one read snapshot. No global writer is held during that work. When counters are unchanged, the response uses that committed snapshot and takes no writer. Otherwise the snapshot closes before writer admission. The short writer verifies selected account identity, canonical file identity, owner/level, campaign/schedule, carry-policy binding and a task/fact signature before persisting the prepared counters. The signature includes accepted period/time, fact floor, all committed counters and the final rowid for that campaign/account after the floor, including later periods. That last detail is essential for the approved carry policy.

The authoritative fact API is append-only; server searches found INSERT but no UPDATE/DELETE of its ledger. The signature therefore detects a new relevant fact without invalidating the operation for unrelated accounts or Town location writes. Same-second task replacement with a different floor is rejected. If preparation becomes stale, the existing SQLite BUSY committed-view deferral is used once; there is no economic retry or invented counter credit. The original claim refresh still computes and commits atomically with mail/stamp/receipt changes.

An authenticated player cannot supply a prepared result or signature: both remain internal values from the selected snapshot. Switched account objects, mutated UID/account and changed resolved database identities are rejected before adoption. Original ownership is checked by the database as well. Failed physical commit propagates and rolls back the prepared update; no prepared counter or success ACK escapes. An unchanged read result is an ordinary committed snapshot, not a promise that no other connection can commit afterward.

## Registered reward regression (high risk shared validator)

Testing the new accepted parent exposed `Potion choice box requires unchanged SQL reader` when claiming the approved attendance reward 716611. The new potion-choice branch unconditionally rejected an ordinary instance even after the existing approved reward catalog registered that template. C4 adopts the adjacent retained-consumable rule: existing SQL wrapper instances retain the unchanged-object contract; templates absent from `VERIFIED_TEMPLATES` still require that wrapper; a previously registered reward follows the complete ordinary item validator. No template is registered by this change, and the acquisition/grant policy is unchanged.

`validate_item` is a shared inventory/mail/wire boundary, so this change has a broader caller surface than attendance. Directed tests serialize every item in all 42 approved attendance reward rows, reject wrong metadata/group/count/slot for 716611, reject an ordinary unregistered 718113 and reject mutation of an existing SQL wrapper. The ready-claim test also checks encoder rollback, replay and one cold mail/stamp/delivery/attachment. Existing pickup and death storage-oracle tests cover the final shared dependencies. Natural box-opening GUI and all other mail item families are not newly qualified by this narrow repair.

## Executed evidence

`attendance-preparation-tests.json`: eleven tests passed on actual Python 3.14.10t with GIL disabled. Includes carry across midnight, overlap union, unchanged/ready/absent no-writer behavior, later-period append, same-second replacement, unrelated-account append, selected-owner/path change, physical commit failure, real writer progress while read preparation is held, original calculator comparison and reward claim/rollback/replay/cold mail. A separate isolated cloud process ran the same eleven tests and exited with no remaining owned PIDs (`cloud-c4-preflight.json`). No player store was copied or changed.

The first final-parent claim test failed before reaching its injected encoder because of the registered-reward regression. That original failing receipt is retained as `attendance-preparation-feedback-parent-failed-v1.json`; the fix was followed by the final eleven-test result. The earlier untested C4 draft omitted the subclass override and was corrected before any execution or release. No draft result is represented as a pass.

## Full cloud comparison and remaining boundary

The complete C4 300-second independent-client SSH comparison passed every action-total check, relay checks, ledger/ACK/cold positions and exact sample counts. Totals P95/P99: death55/68 ms (maximum112), pickup24/41 (maximum69), combined curtain75/88, map90/106 and Town17/36. It still FAILED `waiting_184`:10/35 ms against5/15. All other named queue checks passed. The original production parent was restored ready/running and only owned locks were released. This failed result is retained and is not called a capacity pass.

In its slow B8 records, connection waiting was15–34 ms and the business queue stayed below1 ms. A separate direct-public TCP comparison now uses passive, bounded test-only instrumentation to distinguish inbox backlog, foreground operation waiting and prior upkeep claims. Production source is unchanged by that instrumentation. No scheduling change is justified until attribution is read. The direct test has no successful private5Mbps calibration; actual public TCP and strict calibrated bandwidth remain separate facts.

The shared validator search found direct `validate_item` references in52 production files. The exact registered-template change and all42 reward-row checks therefore remain explicitly high risk despite their small line delta. Final-parent native coin/solo/party test source bindings are archived in `final-parent-native-test-bindings.json`.

The actual C4 compiled launcher selected all2786 signed members, reused2773 from the private C3 cache and fetched13 changed members through local test chunks; repeat fetched zero. Its16 changed engine members preserve the ten feedback repairs and seven own leaves with the one inventory overlap. The compiled endpoint used normalCPU32/IO2, reused its server and stopped normally; its own workspace was removed. These checks do not mean publication or installation.

## Performance limits

The motivating C3 cloud trace showed an attendance transaction holding the writer for about 1448 ms while several deaths and a Town move waited. Its commit stage was about 0.42 ms; this supports reducing writer residence, not attributing the stall to fsync, Defender or the public network. No antivirus, global TCP, durability or checkpoint setting was changed. The latch test proves the new read calculation does not retain the writer; a five-minute cloud run is still needed to measure distribution and remaining stalls. SSH-carried native TLS is explicitly separate from game-port WAN qualification under the user's 5 Mbps limit.
