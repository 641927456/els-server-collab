# C8 differential self-review

Implementing-agent review, 2026-11-06; not human approval. C8 adds transport and periodic-work fixes to the unchanged eight C7 leaves. The accepted player-feedback parent and all ten feedback repairs remain. `review-bindings-c8.json` binds all ten before/after sources to exact Git anchors on64f2f5b1078c5d2db1992fbb156401c3c6c1cd0a. The retained C7/C4 reviews cover the unchanged economic, clock-persistence, attendance and shared validator changes.

## Confirmed permanent clock stall

Actual installed transport source still armed `clock_epoch` from `RealtimeAccess.clock` when0xbd was sent. An independent publication can legitimately skip a busy world lock and be repaired later. Arming from that lagging view permanently bound the stream toNone or the prior part; later correct publications could never match it. This defect was not fixed in C7.

The native before/after test genuinely holds the world lock from another owned thread while the original nonblocking B3/BB publisher executes. It verifies that the view was actually skipped, restores it using the normal application worker, then observes native0x9c. Both initial B3 (missing view) and actual glass-door BB (prior part view) fail to resume in the old code and resume in C8. The same test source and own stores are used before/after; no player state, EXE/KOM or protocol value is changed.

C8 arms the expected epoch from the shared `dungeon_time_sync.context` for the scene whose0xbd just finished writing. The timer still requires a current matching published view and its original registry/member/lease authorization. B2/14a/68 still invalidate the epoch; incomplete/loading/non-game/non-DX11 states still yieldNone from the unchanged helper. Thus delayed publication can postpone a notification but cannot permanently poison the stream. The original nonblocking publication lock order remains; it is not replaced by a world-lock wait while owning a domain.

## Idle authenticated frontend admission

The actual native0x402/0x274 handshake creates a frontend, distinct from the same account's game socket. Its existing upkeep advances `next_periodic` by one second but scheduling previously ignored that deadline and revisited the shared account/world scope every50ms. Only idle authenticated frontends now reuse their actual `next_periodic`. Pending mailbox messages and unfinished slices are checked first and still request an immediate turn. All gameplay/shared-room fast polling retains the original branch.

The actual same-account native frontend/game test passes four cases: idle upkeep is about one second, pending slice is immediate, mailbox message is immediate and an overdue deadline is immediate. Initial fixture mistakes (requesting a nonexistent TLS frontend role, then looking in LOCAL-only session inventory) failed before these cases, were corrected to the existing native handshake/scheduler inventory, and remain in private evidence. They do not represent production defects or successful tests.

## Validation and remaining limits

The unchanged C7 attendance13 and scheduler7 cloud cases, economic rollback/replay/cold ledger proofs and native party barrier/revive tests are reused by their relevant unchanged source hashes. C8's two new sources have the actual native race and frontend tests above. The private compiled V84 selects all2786 members, including these ten leaves and all accepted parent repairs; actual endpoint start/reuse/normal-stop passes. No publication or installation is claimed.

C7 public v3 again passed every server target but Town relay failed (P99>5000ms, maximum10154ms). Its passive receive-to-encode sample covered164908 relays with P95/P99 37/78ms and maximum212ms. Its attempted drain-log hook was replaced by the harness logger, so drain samples were zero; that part is explicitly invalid evidence. C8 uses a tested direct StreamWriter.drain hook and read-only per-socket TCP_INFO counters, without changing TCP settings or packet contents. A two-game/two-frontend smoke matched/drained all ten movements and read real counters with no diagnostic errors. The five-minute C8 public test includes a native frontend for every owned game actor; results are recorded separately. No overall20/40/50-player WAN promise follows from server-only targets or the estimated5Mbps service.


## Completed C8 public20 qualification

The corrected-retirement C8 repeat ran the same300s inputs with20game actors and20actual native frontend handshakes (request628 count20). Every server target and aggregate/steady/burst client relay target passed, as did exact ACK/cold ledgers, source/sample counts, final SQL coordinates, normal drain, no server errors and no remaining connections/runtime. Death57/76ms, pickup25/38, paired door70/98, map86/98, Town17/39; relay98/126, steady98/134 and burst97/112. All158816 forward samples drained; encode-to-drain P99=1ms, maximum3.47ms. Public estimated5Mbps and an independently calibrated hard5Mbps condition remain distinct. Forty-player results are not inferred from this pass.


The separate40-game/40-frontend attempt failed a native entry response deadline after about74s and did not complete the300s window. It had no server errors and drained all own connections/runtime, but cannot qualify40-player capacity or replace the complete20-player pass. Observed NIC peak8.74Mbps; per-socket samples record4.40MB retransmitted against23.03MB sent and225timeout episodes. Receive-to-socket-drain P95/P99 also grows to111/199ms, so server forwarding residence remains a scaling concern alongside network retransmission. Global TCP/QoS settings were only read; ActiveStore QoS is empty. `cloud-native-c8-public40-negative.json` retains aggregate evidence. Larger-scale optimization remains separate from these tested source fixes.
