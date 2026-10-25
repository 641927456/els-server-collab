# Owned mixed consumable selection

Maintainer-approved local policy for existing native quick groups399 and775: filter expired or currently unqualified items, consume earliest finite expiry first, permanent items last, then bag slot and UID. The groups remain independent. This is not an official native priority claim. Unsupported templates remain unsupported; original effect, cooldown, automatic-use, owner, phase and LOCAL/co-op/normal-solo guards remain.

Only storage/consumables.py changes. Capture the default server clock after the real SQLite writer lock so an item expiring during contention is not selected from a stale timestamp. One real transaction still pre-encodes114/115, debits one owned instance, records the existing cooldown/receipt and replays without a second effect. No new item source, schema, timer or client change.

Actual private Application/native Friends TLS verified the original mixed399 refusal, candidate selection for399/775, expiry/lock filtering, exact114/115 template and single UID debit, two rollback points, real writer-lock wait, phase/lease rejection and complete cold2A/8A0. Both current channel inputs and original LOCAL transport passed. UID is the final source-key tie breaker; valid inventory SQL prohibits duplicate owner/bag slots, so no invalid SQL collision was manufactured. Fixture setup and clocks are controlled; natural GUI/battle remain unverified.

Stacked on PR479/a95245, preserving its solo fix and PR475 owned723674 support. Runtime candidates use the real accepted joint online and Root6 local parents; whole snapshots are not installable replacements for later unrelated changes. This source PR does not deploy. Qualified runtime public delivery remains the maintainer separate protected workflow.
