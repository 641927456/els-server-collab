# Native default key map for empty preferences

An account with no saved keyboard map, or an existing empty map, now receives the same-version client native 85-action map through the existing 0x399 message. This restores the default shortcut labels without changing the client. Nonempty account preferences and owned legacy preferences keep their existing precedence and payloads; reading defaults does not create or rewrite a preference row.

This is a one-module server update on top of the account preference implementation in PR #106. It reuses the native map and notification rather than adding input handling, UI logic or client files. The existing authenticated save path and validation remain unchanged.

Validation and delivery:

- The frozen default/custom/empty-row checks and earlier native consumer evidence were reused. New artifact checks passed, followed by independent protected local installation and online installation. Both SQLite databases were backed up through the backup API; original typed rows, schemas and configuration were preserved. Observation lasted 122.56 seconds locally and 127.38 seconds online.
- A newly owned account and normally created role completed authenticated public warm and cold selection. Both complete 0x399 events matched the existing constructor. The map is 352 bytes; the complete payload is 356 bytes including its four-byte result code. The map digest is `9fa8d15175635bb0197b298cb0fb8f238f2aaff0d36726cef75c9a1bbae978b1`.
- Owned items, balances, progression, slots, creation receipt and empty account/legacy preference rows remained unchanged. No key-save or economic wire request was sent. The owned verification account was disabled, temporary publication files and task removed, and publication locks released. Local online-status reconciliation changed metadata only.
- The first commit gate incorrectly expected 352 bytes for the complete payload and stopped before its first remote call or pointer write. A separately reviewed postacceptance correction changed that oracle to 356, retained the successful public result, and restricted execution to commit, reconciliation and cleanup. It did not repeat installation, account setup or public verification.

Local business snapshot: `310eb5152adc54acc57104ada404877c610b8ca4d2d8de54f5f89cc10ce570e0`.
Online business snapshot: `6ed127c5f32440d5be6d816ea3ae6421e3c5b75f1c788a77e972a54324e6fe2a`.
The changed module is byte-identical in both channels (`cff5d73988f3f116dced9a1f515187034533f384e5ed362e77cac07104ea20df`); all previously delivered reforge-transfer files were preserved.

This verification does not claim every character's natural tutorial or GUI flow, customized-key public save coverage, or completion of the whole equipment/growth category. A historical local snapshot display label still names the earlier starter-layout fix; the unit identity, one-file manifest and actual delivery scope identify this key-map update. Frozen historical records were retained.

Private databases, configuration, credentials, account identifiers, captures, runtime packages and the audit/test archive are deliberately excluded from this source change.
