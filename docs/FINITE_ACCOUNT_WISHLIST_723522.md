# Finite account wishlist for 723522

The existing native 1F1/1F2 query and 1F3/1F4 modify flow now persists only the
source-qualified local ED offer723522 (SKU1200723522), visible to its authoritative
Elsword family. The account row is shared across owned roles, while each current
role sees only products allowed in its own catalogue. Other role visibility never
deletes the account row. This neither purchases goods nor creates cash entitlements.

Use the existing fashion/acquisition/ice-exclusion source guards and current lease,
facade, authenticated town, account ownership and lifecycle checks. Immutable source
admission is warmed before BEGIN IMMEDIATE, including a first cold delete; current
player qualification remains inside the transaction. Encode before commit, including
first-use DDL. The only new schema is lazy account_wishlist_items with its composite
primary key. Code recovery preserves player rows; no database rollback is allowed.

Dependency: all six earlier owned-product units must be received/merged first. Their
source changes and the three inherited Git baseline differences remain unchanged.
No new JSON contract or change to the original222 runtime asset lock is introduced.
This supersedes the older1F3 failure-only candidate; that candidate is not another
independent fix and is not submitted separately.

Portable check after provision of the original SHA-locked read-only resources:

```powershell
python -B -X utf8 -m unittest tests.test_finite_account_wishlist_current -v
```

The two-method portable SQLite fixture covers account projection and isolation,
encoder rollback and the first cold-delete source load before the write lock.
Git-context checks use source CI, the staged privacy guard, relevant dependency
ABI/source guards and the minimal inverse increment; results are recorded with the PR.
Prior private SQL/TLS and cold-delete proofs are retained separately.
Private TLS is not a natural widget/public mutation-positive result. Other products,
cash billing/claims and the whole shop card remain incomplete. No client changes,
player DB, credentials, raw native records or private logs are committed.

The protected online and independent local W2 delivery was accepted as
`items-economy-wishlist-claim-20261021-v3`. This Git unit tracks only the wishlist
portion in issue #195; the separate D7D cash-claim refusal is excluded. Git merge
does not deploy or change either server, and natural widget acceptance remains open.
