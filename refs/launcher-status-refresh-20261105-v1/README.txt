Launcher V78 server status refresh, Issue #862.

Archive contains the four exact changed C# sources over deployed V77 and the original assertion harness. Apply only against matching parent source hashes. Unchanged launcher sources/resources and 2121 signed runtime components are resolved from the existing authorized V77 release by SHA; no EXE, private signing key, player state, credential or runtime log is stored here.

The selected endpoint is checked every 10 seconds, including while launching. Mode switches and launch failures invalidate stale observations and request an immediate check. Queries are serialized and read-only: they do not call EnsureRunning. Form disposal releases the timer and prevents control updates. Existing authentication, updater and signed runtime selection remain unchanged.

Actual candidate assembly tests cover disconnect/recovery, negative replies, busy refresh, no overlapping calls, cross-mode and return-to-same-mode invalidation, close during a request, certificate pin failure, public status success, normal Shown and an actual ten-second timer tick. These unchanged results are reused. Publication must separately sign update metadata and verify an old launcher downloads the exact new EXE and the new EXE selects the unchanged signed components. No natural game login or battle claim.
