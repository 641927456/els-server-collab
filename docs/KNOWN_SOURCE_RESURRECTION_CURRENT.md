# Known-source role counter and ordinary solo resurrection

This finite server change joins owned item190556, a known-source role counter C,
the existing login2A field, and the current ordinary native death/continue wire.
It does not implement client HP, MP, damage, animation, timers or interface.

Only the already registered190556 instance is accepted: metadata2, group4, cap1.
Its current RandomItem source explicitly gives10 resurrection uses. Opening one
owned box removes that instance and adds10 to the same selected characterUID C
in one transaction. There is no new grant or acquisition channel. Current unit15
source quests28210/28290/28350 are static evidence; natural acquisition was not
newly tested. Existing inventory definitions and native304-byte proof are reused.

C is a limited known-source compatibility lane. A missing known-source record
reads0 without creating a table. This is not a retail starting allowance, free
daily reset, shared account pool, cash price or pool-order policy. The second
login scalar remains its existing0. Current197,2A and161 consumers restore the
same character Unit+2DB0 absolute count; UID-carrier and indexed2014 UnitUID data
support this scoped ownership contract, not modern official entitlement rules.

Only a currently owned playable lease in loaded solo dungeon30000 stage0 may
continue. Current native A7 and empty AA create the same connection/run/life's
reported-death phases. Exact NPC/actor/envelope checks remain; this is the
native reporting trust boundary, not server-measured HP. The server validates
phase and spends one C atomically, then emits complete161 and162. Native index-1
selects an actual AddStartPos key1..12 from the decoded ordinary line map;
SetTeamStartPos and NPC positions are not substituted. No1-per-run limit is
added: same payload in a later next-sequence native death is a new report.
PVP, special modes, other stages/maps, cash and shared-room revival remain closed.

The existing TCP expected sequence and serialized worker preserve order. A7's
native dying flag guards its producer until native revival clears it. Old
encoded frames are rejected; a deliberately newly encoded next-sequence request
is a new input. The ledger cannot be used as permission to heal a living client.
Open retries prove their original source/operation but rebuild current inventory
and current C in197; they never restore an old absolute count or obsolete UID.
Spent-life retries expose current C without162 or another debit. An unknown
commit-to-send handoff closes the old run and uses existing fresh entry/cold2A;
it does not refund stones, replay an old162, simulate effects or restore a playerDB.

## Storage and code-first recovery

The write side lazily creates exactly `known_resurrection_stones(owner,count)`
and `known_resurrection_spends(operation_id,request_hash,owner,run,life)`.
The latter uniquely binds owner/run/life. Owned-box credit also uses the existing
inventory operation receipt and revision. Owner/deletion and current lease/run
guards are checked inside the transaction before commit. These two new tables
and existing receipt DDL must be declared in release metadata and dual SQLite
API backups; no account/player database is copied between environments.

Recovery is a distinct complete manifest of its actual parent plus three reader
leaves: `storage/resurrection_counter.py`, the readonly counter projection hunk
in `domain/local_session.py`, and first-C-only restoration in
`protocol/local_messages.py`. Keep the new tables and rows. Remove
`domain/known_resurrection_flow.py`, `protocol/known_resurrection.py`,
`storage/known_resurrection.py` and the producer dispatch hunk. The original190556
definition was already readable. A bare parent that sends C0 would hide earned
counter data and is not the compatible recovery contract. Restore verified code
and restart service first, retain backups, full manifests, own QA finally,
health/120-second observation and independent channel pointers. Never roll a
player database back automatically.

## Evidence and future parent

The private runtime evidence covers atomic credit/debit/current replay,
owner/context rollback, two consecutive lives over one legal authenticated TLS
entry, strict old-sequence rejection/lease release, exact cold2A, a real commit
followed by an unknown handoff, and full old-parent reader startup with all
original SQL schema/rows preserved and old open refused. These are source,
transaction and private protocol checks. No natural player GUI/death/HP test,
multiplayer resurrection or official free/cash policy is claimed.

The six-runtime unit has been accepted online and locally as
`items-economy-known-resurrection-20261021-v1`, using independent backups,
code-first three-reader recovery, normal stop/restart and120-second observations.
Public QA validates readonly counter/identity and installed-code boundaries;
positive death/continue evidence is private authenticated TLS. Natural GUI and
multiplayer remain unverified. This repository change does not deploy a server.

Git receives only the four exact new modules and three shared hunks against its
fresh main parent, preserving newer ordinary-skill/Force changes and deliberate
channel differences. Shared full-file Git/formal hashes can differ; verify the
finite forward/inverse bytes and source-qualified bindings rather than copying
formal whole modules. The runtime-asset lock remains unchanged.

Portable tests: `python -B -X utf8 -m unittest tests.test_known_resurrection_current -v`.
The prepared portable methods are compiled, not rerun during source preparation;
the already passed private SQL/TLS checks are reused with explicit ABI/source proof.
