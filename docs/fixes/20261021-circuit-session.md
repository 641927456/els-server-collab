# Current playing lease before circuit installation

A stale selected session could reach circuit installation. Reuse the existing current-lease predicate, require the selected store UID, and pass the authenticated account ID into the existing atomic storage operation. Storage checks ownership before returning even an old receipt.

No client calculation, template, connector, fee, probability or schema changes.

Validation: four focused admission tests; private SQL ownership/replay/rollback cases; actual authenticated TLS stale-session refusal, legitimate installation and cold reload. Public TLS verified a complete native refusal on a newly allocated owned QA account without material grants. Protected online and independent local installation accepted as equipment-session-seal-receipts-20261021-v1, with both120-second observations and full source hashes passed. Natural GUI and whole-card completion remain unverified.

Source-only CI passed (privacy guard,737 Python sources, protocol roundtrip). Tests isolate admission by mocking the resource-backed failure encoder; real artifact codecs were verified separately. Fixture errors remain in private audit evidence. This PR includes no private data or runtime assets.
