# Actual product writer lifecycle: targeted recheck

The stale-remover defect from `independent-product-writer-review-v9.md` is resolved. Only its failing registration-lifecycle input was rerun through the actual product helper in a fresh hidden native helper. The previously passed writer/guard/PVE/PvP/failure/caller inputs were reused without rerun.

The current product registers a one-use `registered` token. The fresh actual-Frida test removes the old pvp registration, registers pvp again with the same append function, and invokes the obsolete remover again. PVP1 remains present. Removing dungeon still leaves that new pvp consumer, and invoking the current pvp remover removes it normally. Receipt `independent-product-writer-lifecycle-v10.json` reports passed=true, no Frida errors, and helper13052 exited0 after cleanup. No game, other process, player storage, physical input or game test lock was touched.

Read-only review also confirms a separate disposed guard at the beginning of the PvP controller's dispose. Repeated old-controller disposal returns before unregistering, detaching or emitting another disabled event, preserving a later controller's ready state. This is a source-level check; the native fixture loads only the actual shared helper prefix and tests its registration token.

Product helper prefix SHA-256:`cbf11183d26b63af305bd03645695764bfa0db4b0416faabfb48206456607cbb`. Full pvp_hp_source.js SHA-256:`d5406f6bf67fe188ce569c8f22e011926a8fabdb76ddd7f134387f476862a3c7`.

The primary investigator's ongoing v15 client loaded its recorded earlier source before this disposal-only fix. Its native battle/report observations must remain attributed to that runtime source. This targeted helper recheck verifies the new disposal registration behavior; it does not turn v15 into a run of the later source or claim natural clear/TAB acceptance.
