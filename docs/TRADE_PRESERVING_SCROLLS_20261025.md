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

## Paired delivery

The maintainer completed paired delivery as `approved-sword-scroll-mixed-policy-20261025-v2` online and `local-approved-sword-scroll-mixed-policy-20261025-v2` locally. Protected observations completed at 127.313 seconds online and 120.383 seconds locally, with save protection and release cleanup accepted. This later documentation commit changes no deployed business bytes.

The controlled public QA used all five original 221 requests, each consuming one owned scroll with zero ED, exact full 222 inventory rows, saved enhancement levels and complete cold inventory. Owned QA account disable, the real writer barrier, exact task cleanup and credential cleanup passed. Natural GUI operation remains unverified. The accepted business source is `e8d1220d7ec269e9eb365620b4f80defc4c18a0c`; the follow-up documentation head is separate.
