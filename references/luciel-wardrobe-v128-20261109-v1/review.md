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
