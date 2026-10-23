# Enforce the current level-dependent ED limit on new NPC sales

New NPC sale proceeds could exceed the current native ED carrying limit. Check the whole batch atomically; committed retries continue to report the current wallet.

Scope: server authority, persistence and receipts only. No client change, schema change or new effect/timer implementation.

Validation: Over-limit and exact-limit boundaries, rollback, batch totals and real private TLS buy/sell/buyback/cold reconnect.

Portable regression: 3 tests passed against private collaboration source and 222 SHA-locked, read-only non-client static resources. Final patch AST matches those tested sources; existing file EOL is preserved. Source privacy/compile/protocol CI passed on this branch. Runtime CI without assets is explicitly separate.

Deployment: accepted online in `items-economy-atomic-receipts-20261021-v1` and independently synchronized locally after SQLite API backups and 120-second observations. Online manifest: `6665f9b96613765c28cb8de91fc4e20dee8ef479fc0a463ecef1d9d83d491b0c`; local manifest: `be8b0812191a2f83d0de443a47205b03bddf732902a184f653fffbb729384fea`. Public TLS acceptance provisioned one dedicated ordinary role, then checked read-only mail/EP with unchanged inventory/wallet and disabled its account. Positive economic/replay/fault cases are private transaction/TLS evidence, not claimed as public GUI tests.

No schema, client, player database, credentials or new runtime resource asset changes. Natural player GUI coverage and other items/economy gaps remain pending.
