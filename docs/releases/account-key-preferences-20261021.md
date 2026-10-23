# Account keyboard preferences

An authenticated account with an empty character roster could receive a successful 397/398 save without durable storage. After character selection, the old character-keyed storage could also restore different keyboard preferences for two characters belonging to the same account.

The current native producer serializes three maps of signed-short key pairs. Its 399 consumer restores those maps or uses the client's existing defaults. The indexed 2014 account database flow corroborates account ownership; it does not supply current key values or default formulas.

The server now stores the validated opaque payload by the authenticated account ID. The first successful save creates an additive `account_key_bindings` table. A transaction commits the payload before success is acknowledged; an identical payload does not increment its revision. Failed SQL writes leave the previous payload intact. Pre-authentication and unsupported phases are rejected. The established 399 notification after 28/2A remains unchanged.

Existing character-keyed rows remain intact. Before the first account save, the server can read an exact ownership-joined legacy row, choosing the lowest owned character UID if several exist. This deterministic compatibility choice is not presented as an official conflict-resolution rule. There is no global UID1001 fallback.

Four portable regression tests cover empty-roster persistence, cold reads and account isolation, duplicate revisions, a real SQLite abort, ownership-bound legacy compatibility and corrupt input. Actual authenticated private TLS checks additionally cover the production session routing, 398 failure responses and cold 399 restoration. Both full composed channel trees passed their artifact checks and source review. The initial Windows test-fixture cleanup failure was corrected by closing fixture connections; it was not a production storage defect.

Release `appearance-config-core-20261021-v1` passed public pinned-TLS acceptance: empty-roster durable save, stable duplicate revision, malformed-request rejection without storage changes, and cold399 restoration for two characters of the same account. The dedicated administrative QA account was disabled afterwards. The ordinary registration limit and all prior account rows remained unchanged. Earlier QA preparation failures are retained separately; they do not replace the successful receipt.

The original native399 consumer was also executed offline: three native maps parsed,85 keyboard entries updated through the original routines, and an empty map entered the original default branch. This is a native-consumer result, not natural GUI acceptance. No client EXE, KOM, script, UI, key event handling, effect or default calculation changes are included. Full natural GUI operation across every role remains a separate acceptance boundary.
