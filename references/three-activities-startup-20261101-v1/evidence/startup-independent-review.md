# Startup UI Hook independent differential review

PASS for the pinned Hook; deployment verification remains required. Reviewer is the receiving publisher, distinct from the author, and did not change Hook source. No critical/high/medium/low security findings were identified. Native-process risk is high enough to require exact identity pins and lifecycle tests.

## Compared change
Both modes: four leaves each, two new. Exact signed V59 archives are the baseline; unpublished candidate has no Git history, so blame was unavailable. Full diff is startup-reviewed.patch; pinned hashes and quantified callers are in startup-independent-review.json. The native cache adapter adds one composition call. Profiles change exactly three artifact records; trace/authentication/connection differences remain byte-identical.

## Critical findings
None. The new wrapper checks EXE and decoded-image SHA and exact composition anchors. JavaScript verifies eleven native byte spans and six vtable slots before installing. Render scope is thread-local and restricted by current vtable; no object address survives a frame. Four draw callbacks forward the original function outside those scopes. Native updates, queue preparation, authentication, timers, database writes and economic qualification are unchanged. Selection and native-dialog paths detach scopes and revert all drawing replacements; repeated finish is idempotent. Partial installation throws after reverting installed sites. Callback objects remain rooted while installed.

## Adversarial and blast-radius assessment
Public network input cannot select native addresses or bypass module pins. A native prompt immediately restores drawing and preserves the pre-existing prompt observer. Other states, later loading, nested scope cleanup and delayed vtable readiness were examined against the supplied native fixture. One direct new composition caller affects both existing native-cache startup consumers (enumerated in JSON). No changed server endpoint, protocol, credential storage or player-data path.

## Tests and limits
Reuse the exact-SHA native fixture, both full script compilation proofs, and owned live-trial-8 first-frame/readback and ten-second selection proof. They cover suppression, original forwarding, identity rejection, prompt/selection restoration, coexistence, retained preparation and cleanup. They do not prove public Friends natural startup or actual signed new dependency selection. Those remain delivery tests, not security findings or claimed passes. No production process was attached during this review.
