# Dungeon startup definitions prewarm

Addresses #830. The first supported dungeon request can load immutable loot catalogs, gate controller indices, fatigue rules and NPC parameter definitions. This delta calls eight existing loaders in Application.start before player stores/listeners open, reusing their validation and caches.

Dynamic player state, qualifications, NPC instances, reward draws, gate progression, receipts and transactions retain their existing consumers. One server file changes; no configuration, database schema, client or launcher delta.

Actual isolated startup proves all eight caches ready before player-store construction, and an invalid static rule fails before player database creation. Genuine source-qualified pet pickups took about23.5/12.7/11.9ms with cold balance checks. These are local TLS protocol results, not natural combat or production load-test claims.

The exact installed base and candidate are archived under base/ and source/. Main's active source predates the installed runtime dependencies and is intentionally not overwritten by this archive. Private runtime resources and existing project reference fixtures are required for the TLS test sources. Databases, credentials, captures and runtime logs are excluded.

Portable source integrity check: `python -B refs/native-dungeon-startup-prewarm-20261104-v1/verify_archive.py`.

Runtime publication is recorded separately after actual installation acceptance. LOCAL and launcher channels are unchanged.
