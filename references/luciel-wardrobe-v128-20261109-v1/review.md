# Differential review — wardrobe V128

## Executive summary

Critical0 / High0 / Medium0 / Low0 findings. Initial risk HIGH because account appearance rights and durable receipts change; residual risk MEDIUM after focused review and transaction tests. Recommendation: accept controlled delivery with explicit forward-recovery boundary. Technical review is not GitHub approval.

## Scope and history

Reviewed2/2 files against exact V126 leaf hashes, also verified identical parent leaves in the V127 signed runtime725b7795. Git history root wardrobe latestb836a7de is an older baseline; release manifests define the immediate base. DependencyPR981/head9fa4e165 is retained. No source divergence to merge for these leaves.

## Findings and caller reach

No demonstrated defect. storage.change has one LocalSession dispatch caller; owner/account checks and the same BEGIN IMMEDIATE transaction precede loaded-owned-item lookup. New register_source has two call sites (registration and apply), preserving account/item/template identity. Shared validate_state has three direct production import sites and retains its old predicate through same_position; historical cross-side state is not newly rejected.

Authoritative source must already be registered; require_owner, acquired-catalog membership, permanent/unsealed and unlocked-target rules remain. Request and chosen positions are checked through the existing native17..28 / +31 pairing. New actor-side restriction applies only to new requests. No UID, position, stats, balance or item count rewrite. No new economic values.

All source registration, binding, appearance, ACK pre-encoding, receipt and final-context validation remain in one transaction. The22-case combined V127 privateTLS Application run proves positive Lu/Ciel use, wrong owner/position/side/dye/lock/timing refusal, partial-batch rollback, final-validation rollback, repeat/cold read and historical cross-side read/correction. Native accessory17/48 definition validation is reused with identical data.

## Persistent receipt compatibility

New apply receipts serialize{uids,registered}; retries return only the registration keys of the original operation. Legacy UID-list receipts still replay without migration. This is a durable format extension with noDDL. After new writes, code recovery must retain the new reader or forward-fix. The release controller retains newly started readers and refuses old-code rollback after candidate start; it never restores player DBs.

## Adversarial review and limits

Owned inventory comes from owner-scoped load_items; a foreign/missing target cannot enter registration. Register identity conflict throws, and a later bad target or bad context rolls back earlier insertion. Registered appearance entitlement and dye variant are checked before apply. Request hashes and owner/account/kind bind replay. Historical malformed or manually corrupted databases are outside this patch; no speculative fallback added.

Integrator reviewed other-author code independently. Exact two candidate hashes and realTLS results are bound; this is not a full economy audit. Public deployment and naturalGUI are separate from this source review. No new native Hook or binary change.

## Approved per-character campaign addition

Reviewed4/4 additional peer leaves; total6/6 runtime delta. This is an explicitly approved server rule: each owned level99 third-job character participates once. Existing numeric rewards and qualification remain. All campaign account/task reads and writes in production occur in these four files; snapshot, join, tasks, task awards, reward masks, points, weapon box and permanent conversion now include both account and character. Three external production consumers are the native580 provider, weapon-box handler and points-item handler. No account-only campaign writer remains in the candidate. Run receipts retain their preexisting run/account/character identity and one-time proof.

Startup initialize runs in the provider's BEGIN IMMEDIATE transaction. It identifies old character non-PK schema, renames the two old tables, creates composite-PK tables, copies all original account ledger columns unchanged, joins old tasks to the original participant, and drops temporary tables. A task lacking a participant fails its NOT NULL insertion and rolls the transaction back instead of assigning invented ownership. New schema is idempotent. There is no DB restore and no change to weapon UID/options/runs.

Ten tests pass in the combined V127+six-leaf environment: two-role independent join/tasks/points/tiers/conversion, owner/stage refusals, replay, cold original-protocol restoration, inventory/encoding rollback, unopened/opened/permanent legacy records, repeated migration, and deliberate DROP failure with exact old SQL rollback. Exact six imported-module bindings are recorded independently of the test report's original candidate-directory inventory.

Initial risk HIGH (schema and economic grants), residual MEDIUM. No demonstrated defect found. Actual online and local pre/post migration preservation readbacks are required at deployment. Candidate installation must retain new readers/writers before the first migration-capable check and use forward repair after any possible new-format write. Never revert to old account-only writes after multiple participants exist. Public TLS and naturalGUI are separate acceptance layers.
