# Owned trade-preserving enhancement scrolls

The existing handler rejected five owned scrolls because only four fixed-level scrolls were admitted. This change applies the user-approved local server policy below. It does not assert the original client meaning of `ENABLE_TRADE=0`.

| Scroll | Fixed enhancement |
| --- | --- |
| 132495 | +5 |
| 132496 | +6 |
| 132497 | +7 |
| 132498 | +8 |
| 60007270 | +7 |

A successful original 221 request consumes one scroll and zero ED. The target must satisfy the existing normal, owned, unequipped weapon/armor qualification and strictly increase in enhancement. Target metadata, seal state and other trade-related state remain unchanged. No scroll acquisition source is added. Each approved source row must exactly match its ID, fixed level and `ENABLE_TRADE=0`; other unknown restrictions remain closed.

The original transaction, owner/current lease checks, lock and expiration checks, complete 222 event encoding before commit, receipt replay and enhancement-progress transition are retained. No new schema or client behavior is introduced.

Private validation used fresh actual Applications and native framing: the online parent refused all five; candidates passed 14 Friends/TLS checks for each channel and 13 actual LOCAL/TCP checks. These cover all five fixed upgrades, exact one-scroll/zero-ED deltas, sealed/unsealed state preservation, native 222 rows, cold loading, receipt replay, equal-level refusal, preencode rollback, changed-policy-row refusal, lock/expiration and session gates. Previously qualified unchanged boundary evidence is reused. An initial receipt-export BLOB serialization failure is retained in private evidence; candidate business bytes did not change.

This is source/private qualification. Formal installation, public QA and natural GUI operation remain separate maintainer actions.
