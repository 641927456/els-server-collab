# Static dungeon readiness and cancelled periodic publication

Addresses #832. Complete40 verified static loader/import entries at server startup, build an immutable type map for all740 native dungeons once, and warm fixed HP categories/factors for276 finite policy IDs. Existing live eligibility, RNG draws, cooldowns, reward receipts and transactions retain their original consumers.

A foreground request can cancel a pending periodic claim after its slice has entered world admission. The old all-cancelled slice still published routing/registry snapshots in finally, holding the world gate despite no member execution. Publish only when a member actually executed; started/error and mixed-member paths keep their original publication and completion semantics.

The deterministic test holds only the owned test publisher for92ms: baseline foreground wait93.19ms, candidate0.33ms, cancelled publications1 to0. It exercises actual gate, queue, claim, slice and scheduler foreground code. It proves this race; the historical production92ms timing did not identify its holder. Real started transactions are not interrupted.

Actual candidate startup checks40 entries before player stores; all740 type values match native definitions and lookups perform no catalog opens. Virtual IDs reject, the map is immutable, and invalid static input fails before player DB creation. Owned TLS pet pickups took15.8/12.5/13.1ms with cold balances verified. These are isolated protocol tests, not natural combat or production load-test claims.

Exact installed base/candidate bytes are archived under base/ and source/ because main's active source predates runtime dependencies. Test sources require the project's private pinned resources/reference fixtures; the portable integrity check requires only Python:

`python -B refs/native-dungeon-static-ready-queue-fix-20261104-v1/verify_archive.py`

Three runtime server files change. No credentials, databases, captures, runtime logs, client, launcher, configuration or schema changes are included. ONLINE publication is recorded separately; Git submission does not imply main merge or LOCAL installation.
