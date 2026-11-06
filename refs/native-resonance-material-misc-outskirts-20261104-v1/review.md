# Cumulative gameplay candidate differential review

Self-review of the 31-file SHA-pinned candidate against `native-dungeon-static-ready-queue-fix-20261104-v1`. This is not a GitHub approval or merge exemption.

## Result

No unresolved newly introduced high/critical security issue found within the reviewed paths. Production acceptance remains a separate required delivery step.

The compatibility finding was real: restoring the exact old registry after a new-material drop would make four saved templates unreadable. The qualified recovery retains five reader/support leaves, closes generic production and restores prior producers. Two fresh processes verified candidate writes followed by recovery cold read/full inventory encoding, with all four generic grants rejected and no database restoration.

## Scope and history

31/31 changed files compared. Authentication/actor ownership, acquisition sources, NPC debit/grant, shared death commit and replay paths received focused review with direct consumers. Snapshot provenance is pinned by complete hashes. Exact historical blame is unavailable for the deployed snapshot; the current Git main is older and will receive an exact source/base archive rather than an unsafe root overwrite.

## Caller reach (resolved imports only)

| Target | Call sites | Locations |
|---|---:|---|
| `els_server.storage.raid_reward_actions.open_box` | 1 | els_server/domain/raid_reward_flow.py:92 |
| `els_server.storage.dungeon_equipment_loot.issue` | 3 | els_server/domain/dungeon_equipment_loot_flow.py:117, els_server/domain/friends_material_loot.py:270, els_server/domain/native_script_loot.py:171 |
| `els_server.domain.ordinary_misc_loot.source` | 4 | els_server/domain/dungeon_equipment_loot_flow.py:115, els_server/domain/friends_material_loot.py:269, els_server/domain/legacy_pve_exp.py:79, els_server/domain/pve_economy_flow.py:175 |
| `els_server.storage.raid_economy_state.prepare_batch` | 1 | els_server/domain/raid_economy_flow.py:142 |
| `els_server.storage.material_exchange.exchange` | 1 | els_server/storage/purifier_exchange.py:8 |
| `els_server.domain.giant_misc_loot.group_death` | 1 | els_server/domain/friends_dungeon.py:422 |

Counts are conservative static import resolutions, not a complete dynamic call graph. Character creation and the inventory registry additionally affect all native creation and inventory load paths.

## Changes

| File | Added | Removed | Risk |
|---|---:|---:|---|
| `els_server/application.py` | 2 | 0 | MEDIUM |
| `els_server/data/dungeon_material_loot_catalog.json` | 130 | 4 | MEDIUM |
| `els_server/data/formal_npc_hp.json` | 236 | 0 | MEDIUM |
| `els_server/data/formal_npc_hp.manifest.json` | 1 | 1 | MEDIUM |
| `els_server/data/ordinary_misc_loot.json` | 6458 | 0 | MEDIUM |
| `els_server/data/ordinary_misc_loot.manifest.json` | 4 | 0 | MEDIUM |
| `els_server/data/regional_drop_materials.json` | 922 | 0 | MEDIUM |
| `els_server/data/regional_drop_materials.manifest.json` | 4 | 0 | MEDIUM |
| `els_server/domain/dungeon_equipment_loot_flow.py` | 5 | 4 | HIGH |
| `els_server/domain/dungeon_flow.py` | 3 | 0 | HIGH |
| `els_server/domain/dungeon_material_loot_catalog.py` | 21 | 9 | HIGH |
| `els_server/domain/fishing_bait_loot.py` | 1 | 1 | HIGH |
| `els_server/domain/friends_dungeon.py` | 3 | 0 | HIGH |
| `els_server/domain/friends_material_loot.py` | 26 | 24 | HIGH |
| `els_server/domain/giant_misc_loot.py` | 79 | 0 | HIGH |
| `els_server/domain/inventory_items.py` | 6 | 0 | HIGH |
| `els_server/domain/legacy_pve_exp.py` | 5 | 1 | HIGH |
| `els_server/domain/local_session.py` | 5 | 0 | HIGH |
| `els_server/domain/ordinary_misc_loot.py` | 139 | 0 | HIGH |
| `els_server/domain/pve_economy_flow.py` | 4 | 0 | HIGH |
| `els_server/domain/raid_reward_items.py` | 13 | 3 | HIGH |
| `els_server/domain/regional_drop_materials.py` | 26 | 0 | HIGH |
| `els_server/domain/regional_material_exchange_flow.py` | 34 | 0 | HIGH |
| `els_server/domain/resonance_allocation_flow.py` | 1 | 2 | HIGH |
| `els_server/storage/characters.py` | 8 | 0 | HIGH |
| `els_server/storage/dungeon_equipment_loot.py` | 23 | 5 | HIGH |
| `els_server/storage/material_exchange.py` | 49 | 0 | HIGH |
| `els_server/storage/ordinary_misc_loot.py` | 64 | 0 | HIGH |
| `els_server/storage/purifier_exchange.py` | 7 | 64 | HIGH |
| `els_server/storage/raid_economy_state.py` | 3 | 0 | HIGH |
| `els_server/storage/raid_reward_actions.py` | 4 | 3 | HIGH |

## Concrete adversarial checks

- Forged template/drop ID, stale epoch and unrelated map cannot gain the typed source. New material acquisition remains source-only; Change-A admission only extends exact current final-stage giant Boss issues. Wrong-map and Change-E substitution tests reject.
- Repeated AD/D0/native use/NPC exchange/final phase uses immutable committed issues/receipts. Existing historical results are not topped up; no endpoint accepts the client-provided item count as a grant amount.
- Material exchanges bind active actor, saved/current town, native recipe, unlocked ownership, quantity and session generation. Encoding failure, full bags and post-encoding lease revocation leave no debit/grant increment.
- Shared giant drops, quest event writes and prepared member mailboxes are committed once for all current members. A late encoder fault rolls back all SQL and preserves all original member run/drop state.
- Large material boxes split into existing <=999-unit factory plans inside the same transaction. The shared NPC writer similarly respects plan limits; actual 10000-yellow-crystal use and nine native NPC recipe flows pass.
- No new packet auth/crypto, raw game modification, player-process access, credential publication or player-database restore path was introduced. Authenticated AD combat-report trust is inherited; authoritative damage simulation is not claimed.

## Evidence and limits

61 targeted cases (24 ordinary,19 completion,18 material regression) passed in bounded runs, plus9 offline original-machine-code reader/constructor/enumerator cases. Unchanged related passes are reused. Three unchanged ERP cases and314 HP source checks retain original evidence. Actual installed process/public native protocol and120-second observation must be recorded by publication. Natural GUI/combat, load testing and every random branch remain unverified.

Recovery compatibility verification: `recovery-reader-verification.json`. Complete per-case hashes and scopes: candidate `qualification.json` and delivery `review-scope.json`.
