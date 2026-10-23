# Native Tenebros storage capacity

This server change supplies capacity expansion for the four verified parts (0..3). The authorized local-server policy shares capacity by account and charges the current character 2,000,000 ED per successful +1 slot, from 3 to at most 6 per part. Account sharing and the per-action step are local rules, not claims about official rules.

The implementation adds three modules and only three integration hunks in local_session: synchronization, request dispatch and periodic invalidation. Current enabled actor/session/character, existing NPC10381/town20013 static service binding and existing level99/quest26690 admission are checked before the same real SQLite transaction debits ED and updates shared capacity. Complete encoding and actor revalidation occur before commit; durable receipts and cold projection synchronize the result. No NPC interaction token or client behavior is fabricated.

NEW SCHEMA: account_tenebros_capacity and tenebros_capacity_receipts are additive lazy tables created only within the first successful native9F2 transaction. There is no startup/install DDL or replacement of account/player tables. The reviewed schema digest is c89dba0a8badc77fffe1fbc08c9a6d9f0c2b2fec4cd7a7d0e88e5a4fec379dfa. Code-first rollback/cold-login evidence preserves committed ED and both new tables; it does not restore a player database.

This is capacity only. It adds no option store/withdraw/conversion, sources or persisted nonzero option support. On the pinned parent without an option writer, native9F1 replaces the complete four-part map with six zero option IDs per part; arbitrary client nonzero option values are not preserved. A future option writer must supply authoritative vectors or refuse incompatible state.

Pinned native codec/static consumer contracts and existing controlled real Application/SQL/private TLS, periodic, rollback and cold-login evidence are reused. Public production QA and natural GUI are unverified. Final actual-parent qualification, independent source review and protected delivery remain separate from Git preparation. No private SQL, fixtures, dumps, captures, credentials or runtime logs are included.
