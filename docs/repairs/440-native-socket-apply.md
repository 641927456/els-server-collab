# Native magic-stone Apply

The original1C4 roll now stores a pending result instead of changing effective equipment options immediately. The original8B1 Apply accepts only the original or latest server-generated choice for each slot, for the same character, item and session; successful8B2 also refreshes existing town peer appearance.

Stone and ED consumption retain the existing roll timing. Apply adds no fee. Pending state, consumption, effective changes and receipts use the existing real SQL transaction, precommit full-event encoding and current-instance replay. One additive lazy table is created inside the transaction; no install DDL or client changes are included.

Validation: both runtime variants passed29 actual private Application/TLS checks, including rollback, stale session/target rejection, repeated roll and current-state replay. A combined candidate also preserved original221 enhancement-scroll behavior and cold inventory loading. Natural GUI close/cancel and multiplayer combat are unverified; no new refund rule is inferred.

This PR stacks on #441. Runtime and public source retain their existing distinct guarded enhancement branches; only the socket branch and successful peer projection are shared. Runtime publication is tracked separately and is pending at PR creation.
