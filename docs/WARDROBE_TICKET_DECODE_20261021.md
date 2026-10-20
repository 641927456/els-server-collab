# Preserve ordered item decode failures

Follow-up to PR71. The page compiler now gathers raw record/stats/stat_bonus fields in bounded read-only batches, then performs the existing ClientData.item stats unpack and bonus conversion in the original allowed-template sequence before reading record[210]. A later truncated row cannot mask an earlier stats/bonus or unknown-template failure. No player state, resources, acquisition rule, protocol bytes or client behavior change.

Frozen source SHA256: `ea6b7d3aa08fb6c8706de55734e9bda1e176efe38fd29d17b007a1991e47d585`. PR71's source, freeze and 90 valid-response comparison remain historical evidence; this revision changes only the private page compiler. Private validated real ClientData packs reproduce seven prior exception differences and confirm exact original type/message/order restoration. One current page with force0/1 remains byte-identical, taking one cold connection and zero warm connections. The unchanged complete valid-data comparison is reused.

Portable tests use synthetic private SQLite rows and cover the new ordered failure contract alongside batching, source keys, force/order/duplicates, concurrency and the64-entry bound. Run `python -B tests/test_wardrobe_ticket_pages.py`. This does not need runtime assets or player saves.

Controlled online/local installation remains pending with the maintainer at this commit; Git merge does not deploy. Natural player/GUI startup remains unverified. Existing immutable pack validation and new-instance-on-pack-change semantics are retained.
