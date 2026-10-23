# Seal receipt replay uses current item locations

After a committed seal/unseal operation, moving the target or remaining stamp could make a replay return stale slot contents. Replay now uses the existing current_changes helper for270/272, resolving the original instance UIDs at their current positions and preserving a replacement occupant at the old position. It does not spend another stamp or alter qualification, seal limits or original economics.

Validation: focused current-position regression; private SQL atomicity and exactly-once checks; actual authenticated TLS270/272 and cold reload after controlled item moves. The replay fixture deliberately reuses a committed operation ID and is not claimed as a natural GUI retry. Public TLS checked complete rejection ACKs without item grants. Protected online and independent local installation accepted as equipment-session-seal-receipts-20261021-v1, with both120-second observations and full source hashes passed. GUI and whole-card completion remain pending.

Source-only CI passed (privacy guard,737 Python sources, protocol roundtrip). Initial fixture errors are retained privately. No player databases, credentials, captures or runtime assets are included.
