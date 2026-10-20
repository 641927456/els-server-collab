# Static cold-load reads

Cold imports rebuilt the same Enum slot mapping thousands of times and opened a static-catalog SQLite connection for individual item proofs. This is reached by the launcher's separate preflight/probe Python processes and by server cold imports.

Three source leaves now reuse an actual-JSON-bound enum map, use immutable read-only queries bounded to256 parameters, and pass transient proved manufacture fashion records through the original ordered registration loop. Original policy/client/record identities, item stats/bonus decoding, minor-role/named-slot checks, malformed-key fallback and error order remain. No global item pool, player cache, schema, source/rate/fee or gameplay rule is added.

Private qualification reused each target's exact old baseline. All four complete inventory maps,3,120 ordered slot input/results and21,734 manufacture definitions were identical. Cold imports measured34.212→3.046 seconds for launcher support modules,31.686→2.884 for the online parent and31.826→2.909 for the local parent. Static connections fell from about61,000 to about4,700; Enum decodes fell from about3,120 to2–4. These are individual cold-import samples, with candidate processes concurrent, and do not claim end-to-end GUI latency.

With the same pinned native reference input, one new pure bridge-source call produced the same26,933-byte output as the prior consumer: SHA256 `e409b19342305f400d08f7085551b87d0684be9eeda5f6bee319639941387b14`. No generated JS was written or executed. Game EXE/KOM, resources, JS, probe and Hook behavior are unchanged.

Run `python -B tools/check_cold_definition_contracts.py` for eight resource-free synthetic contracts, including decode/error order, enum identity, bounded batches and static-proof rejection. Standard checks are `python -B tools/ci_checks.py`. Private full-pack results are reused; no game or player database is needed by these portable tests.

The repository inventory file retains the latest main changes; only its manufacture block is replaced. Deployment-channel variants must retain their own parent contents and are not forced to have identical complete-file SHA. This Git change does not deploy a server or launcher. Protected delivery and actual channel acceptance are maintained separately.
