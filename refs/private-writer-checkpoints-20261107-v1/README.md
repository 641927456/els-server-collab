# Private writer checkpoints

Player transactions retain SQLite `synchronous=FULL` and return success only after the physical commit. This candidate builds on PR #919's FIFO writer admission and batch yielding.

`Application.prepare()` starts and warms the existing WAL checkpoint owner before preparing the coin, death, clock and town position writers. Each of those four private connections disables its automatic checkpoint once, before its first transaction. The existing background PASSIVE checkpoint worker owns that work until the private writers have drained and closed. Standalone writers retain SQLite's default automatic checkpoint policy. An unavailable checkpoint owner or a different save file is rejected before mutation. There is no policy-restoration SQL after a successful commit.

On Windows the checkpoint thread uses below-normal CPU priority with normal I/O priority. The former background processing mode lowered I/O priority while sharing the database file with player writes. Slow commits and a long clock transaction overlapped checkpoints in the 50-actor diagnostic; the negative measurements are preserved. This is evidence for the scheduling change, not a claim that every storage stall has the same cause. Microsoft documents the shared-resource priority inversion risk in [SetThreadPriority](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-setthreadpriority).

The accepted runtime parent contains PR #920's dungeon statistics finalizer. Its exact application source is pinned under `runtime-parent`; the candidate preserves that behavior while changing writer startup order. The runtime parent is installed but that source PR is not part of the base Git commit. The source bindings distinguish the runtime parent from the Git parent.

Eight isolated real-SQLite tests cover all four managed and standalone writers, FULL policy, no policy SQL after commit, owner failure, wrong-save rejection, rollback, reader gaps and abrupt process exit after an acknowledged write. The portable CI fixture uses explicit gameplay doubles; the separate native financial regression receipts exercise actual economy, title, replay and rollback paths. Process-exit recovery does not prove power-loss behavior.

`local-native-current50-five.json` records the full five-minute local result and its exact source binding. This test uses 20 town and 30 dungeon game connections on four selected logical CPUs. It does not include idle frontend connections, the native 9E statistics stream, natural GUI combat, a 5 Mbps shaper or the production hardware. Source submission, installation and public peak-capacity acceptance remain separate.

An earlier temporary disable/restore prototype was rejected after it reported an error after a durable commit. `rejected-temporary-restore.json` preserves that finding; the rejected implementation is not part of this candidate.
