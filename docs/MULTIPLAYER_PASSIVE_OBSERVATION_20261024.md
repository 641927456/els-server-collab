# Bounded34320 multiplayer passive diagnostics

The old trace stopped permanently on a multiplayer participant set, covered only118178, and recorded D0 as kind/hash. Direct request-return tracing also could not attest peer mailbox egress. This patch closes that diagnostic coverage gap only; it does not establish or fix a new gameplay defect.

Only the observer and transport change. The observer accepts bounded2..4 owner contexts and118177/118178/118186, reuses the existing D0 decoder, distinguishes returned receipt hints from new awards, and logs original CF/D2/D3/2D0 after successful socket drain. Recipient context includes shared-run and per-owner reward identity so equal drop IDs do not merge owners. Snapshot drift remains unknown; exact34320 CF/D2 payload facts survive in the live dungeon phase. Town and other maps do not inherit the scope latch. D3 remains size/hash only and its last receipt hint is explicitly not proof that this D3 awarded items.

Record/byte/time limits include terminal records. Logging and snapshot failures cannot replace business results. Original bound Application.call sites, timers/after_reply, mailbox drain, wire encoding/order, actor methods, SQL, material issuance/probability and client behavior remain unchanged.

## Validation and limits

Independent source review passed. New controlled observer fixtures cover2..4 owners sharing the same drop ID, all three material templates, one archived original native mode0 D0 witness, receipt attribution, unknown contexts/town scope, budgets and logger failures. The existing native serializer and20-mode qualification were reused; they were not rerun.

The original GameServer constructor/start/accept/handle/send/close ran over actual private loopback sockets with explicit lightweight Application and business-session stubs. The request reply and peer periodic paths emitted six post-drain records. Controlled write/drain/timeout failures emitted zero success records. Across five new baseline/candidate profiles, complete private fixture wire bytes, order, sequence and business-stub results were identical; observer-specific sink failure stayed fail-open. Formal SQL/database-file access, client/native operations and remote requests were zero. actualApplication=false, native=false, natural=false. A returned receipt was a copied fixture, not a SQL-positive test.

This is one diagnostic unit, two source leaves, zero new gameplay repair units. Server drain is not client receipt. Natural visible world creation, acquired fade/disappearance, and multiplayer personal material pickup remain unaccepted. Runtime/channel delivery requires separate maintained receipts; merging this source PR does not deploy it.

## Immutable review references

- Source contract: `96496d86b00b0665ae727d11dfface0c62835bdd9923146ae0b13cf94c413661`
- Independent source review: `df7d08899f35cfea77adbf75d9f666f29c0a2abd75b7a98790ad1bfcce71c295`
- New diagnostic result: `6b2e0a230938832c6699092a27efa19f93359fa3bc95e459032626b2b57901fc`
- Local verification: `c72df1db19d6e18e329e52d2dbb132d578a2ce7ffbcb968959cb91bef484829f`
- Online source-bound reuse: `b36a8439dcc543df6d9df31a8d759675525c443dcb738cfb02fe26101c5f08aa`
- Observer candidate: `12c659a6b2f0c21cc776d29a99a34753dcb98135bd7e9a5bfaa3faab9933b877`
- Transport candidate: `b3aa5bf7897ca9ea46ce790724bcc21760311c0b9a682442b0a601249bf995db`

Online evidence is reused for this new diagnostic only.26 imported business modules match byte-for-byte; config has only the unused local selected-pack field/check/load-list difference, and transport uses only the identical SessionOrderError class from local_session while real account/session classes are unused. The relevant normalized AST contracts and native decoder data match. Full source trees and intentional channel differences are not claimed identical. Host Crypto dependencies retain their existing qualification; the online business snapshot does not contain vendor files.
