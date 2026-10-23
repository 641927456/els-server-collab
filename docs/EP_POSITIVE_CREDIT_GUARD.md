# Positive EP credit transaction and revision guard

Positive EP credit now requires the caller's existing SQLite transaction and a
saved revision that is a strict integer in [0, 2^63-1). The last permitted
increment from MAX-1 to MAX remains valid; another positive increment refuses
instead of allowing SQLite to promote the revision to REAL. Malformed saved
revision values also refuse. This is a corruption/overflow boundary, with no
claim that a normal player reached MAX or exploited a concurrent lost update.

Only four guard lines change in storage/ep_points.py. Existing ensure and balance,
zero-amount no-initialization/no-write behavior, owner validation, 10000 EP cap,
table schema and successful UPSERT remain intact. Both direct production callers
(conversion and quest action) already enter BEGIN IMMEDIATE and pass the same db.
The caller owns rollback of all lazy schema, economy, quest rewards and receipts.

Prior private evidence reproduces the old REAL promotion, verifies malformed/MAX
refusal and the MAX-1 final integer, and rolls back the complete quest22337 claim.
Those SQL/TLS successes are reused; this draft only compiles and checks exact
source boundaries. Run tools/check_ep_credit_source_boundary.py after staging the
actual Issue branch, then run the repository's required source CI before submit.
Compilation is not business, public TLS, natural GUI or deployment acceptance.

No new schema, reader, client behavior, SKU, shop/debit path, probability or clock
change. No database repair/reset is performed. Code-first recovery retains player
data. Protected online and independent local acceptance is complete for
items-economy-material-ep-credit-20261021-v1, including backup, observation,
read-only public QA and cleanup. This separate source PR retains the actual
parent and checks its Git-stage source boundary; it does not deploy or rerun
the prior business proofs. Material130047 is tracked separately in PR218.
