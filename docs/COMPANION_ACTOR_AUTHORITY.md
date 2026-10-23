# Existing companion activation: authoritative actor and saved owner

Generic permanent-pet/mount activation and pet summon could accept a pending,
deleted or foreign-owned actor before replaying a saved receipt. This fix
requires the current selected UID and authenticated account lease, then checks
the active saved character and account owner inside BEGIN IMMEDIATE before
DDL or an old receipt. The enabled Dana early activation uses the same guards.
Optional account_id preserves the existing legitimate offline calling ABI.

Exactly three existing server Python files change. Existing native creation,
AI, effects, growth, expiry, timing and notifications are reused. There are no
new items, EP offers, tables, migrations, readers, client files or shared
LocalSession replacement. Four EP pet purchase/reader admission is separate.

The exact increment was accepted online as
items-economy-companion-actor-20261021-v1 and independently locally as
local-items-economy-companion-actor-20261021-v1. Protected maintenance included
channel-specific SQLite API/code/config/task backups, normal stop, online
121.46-second and local124.21-second observations, unchanged own saved data,
and exact stage/task cleanup with owned lock release. The dedicated QA account
was disabled at closeout. Player/account databases were not copied across
channels or rolled back.

Public TLS acceptance covered the existing owned login/selection/town/bank
read flow, unchanged own inventory/balance and three installed module paths
and SHAs. It did not perform public positive activation or fault injection.
Previously frozen private SQL/TLS evidence for pending/finalized/wrong-owner
rejection, valid activation and same-operation replay is reused. Natural GUI,
positive public pet/mount activation and general pet-system completion remain
unverified. The portable source checker verifies exact targets and selected
helper/dispatch ABI without opening DBs or importing game/network code.

This source receipt preserves unrelated activity, equipment, world, wish-list
and local-initializer changes from the actual Git parent. Rollback is the
three old code files plus service recovery, with no player-data rollback.
Git submission does not redeploy either accepted server or rebuild a launcher.
