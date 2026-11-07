# C7 differential self-review

Implementing-agent review, 2026-11-06; this is not human approval. Eight exact source leaves apply to the accepted player-feedback parent (manifest f60e41011b442851d8f36e4785d52cd0d0eb7c4f5e61040aee053df28e17b7fc). `review-bindings-c7.json` records matching Git source anchors on 64f2f5b1078c5d2db1992fbb156401c3c6c1cd0a. All ten feedback repairs remain. The C4 review is retained for the unchanged writer, clock, read-preparation and shared validator analysis.

## Scheduler followup admission

The prior cloud traces attributed slow B8 admission to an already-running upkeep turn, with request/business queue waits below 1 ms. A reply can trigger a native followup before the next existing 50 ms poll interval. The scheduler now defers selecting a fresh quiet upkeep turn until that interval expires; the existing one-second fairness limit still bounds postponement. This does not cancel or release a started transaction. Already-reserved operation waiters retain their FIFO ownership. Pending notifications bypass the grace.

C5 incorrectly changed the real `due` while arming grace; a newly arriving notification could then wait behind grace. The seventh async test reproduced this failure, retained as `periodic-followup-c5-armed-notification-failed.json`. C7 leaves `due` intact and uses per-iteration wake deadlines. A notification wakes the scheduler against its original deadline. All seven cases pass on the exact cloud C7 source: followup ordering and eventual poll, unread notification, notification arriving after grace is armed, stale fairness, maximum grace bound, existing reserved waiter and running transaction retirement. The scheduler's sole transport foreground/notification entry remains unchanged. No extra world queue, economic retry or early ACK is introduced.

## Native attendance display cache

The original native view publishes `online_seconds // 60`. C7 compares the same minute, clear count and readiness when deciding whether an incomplete display cache needs a commit. Authoritative clock facts and progress still persist every observed second; the exact original refresh runs inside accept/claim transactions. The first ready transition and each qualifying clear still commit immediately. Policy binding, selected owner/file identity, immutable fact signature, stale BUSY result, full claim/mail/stamp/receipt transaction and commit-before-ACK are unchanged.

The thirteen attendance cases include the prior eleven preparation/rollback/claim tests plus 65 durable one-second observations (only the native minute change writes display cache, cold reconstruction yields all 65 seconds) and five real qualifying clear transitions. The exact source and test hashes pass in a separate bounded cloud process with GIL disabled and no remaining PIDs. C7's actual native two-member party, dead guest barrier and original revive tests also pass. The unchanged writer/original solo-gate proofs reuse their exact source hashes and retained final-parent oracle results.

## Measured performance and limits

The C7 second public five-minute 10-Town/10-dungeon run passed every server total and queue target, with exact economic ACK/cold ledger checks, exact samples, final cold coordinates, normal drain and no server errors. P95/P99 in milliseconds: death 56/73, pickup 21/36, map 88/95, paired glass door 70/75, Town movement 15/36. Death queue 2/5; pickup 2/3; map 2/2; B8 3/3; BB 2/2.

That run FAILED client Town relay: P95/P99 116/694 ms, maximum 2138 ms; the client loop lag was only 12/15 ms. Thus it does not qualify overall public capacity. A further same-source test with passive receive/encode/drain attribution is in progress. The failed first C7 public attempt stopped during TLS admission and is not a latency result. Forty-player qualification has not run. Neither this actual-public test nor SSH comparisons establish a hard calibrated 5 Mbps condition. Local C4 50-player diagnostics do not qualify C7 public 50-player capacity. No TCP, antivirus, durability, checkpoint or player database setting has been changed.

The private compiled V84 selects all 2786 signed members, matches all eight C7 leaves, preserves the ten parent repairs, and passes repeat selection and actual endpoint start/reuse/normal-stop checks. It is not published or installed. Public V83 remains the parent. Source CI, human exact-head merge approval and actual installation are separate remaining steps.
