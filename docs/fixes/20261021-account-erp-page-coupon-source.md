# Account-once ERP page coupon quest53520 source

Issue #226. Native AccountQuest53520 was absent from the server catalogue,
and character-only task rows could not preserve account progress or an
account-once reward when switching characters.

This finite extension reuses the existing quest, inventory, transaction and
full response encoders. It admits only the current same-client quest53520,
with saved level99 and authoritative enabled account ERP100, its exact
100-clear exclusion list, and one712413 reward. The first acceptor carries
the original wire owner; other characters of the authenticated account
share its active/completed state. Account/run receipts bind only actual
committed owned reward and assessment records after acceptance. The
current active recipient receives the item once; retries never copy a
different recipient's inventory delta.

Client SHA: `6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709`.
Normal eight-leaf freeze: `672fa1b0e54654baf98554da34f80fa48cc6afd8a0eef3f77732c365bdcdf402`.
The 2014 account-quest manager supplies shared carrier/projection flow,
while the current quest record supplies IDs, level, ERP, exclusions and reward.
The current CN guide also describes this account-once quest source:
https://els.ztgame.com/game/003-1635-00307-850051.shtml?ms=775

Private authenticated TLS and transaction checks cover cross-character
99-to100 continuation, fullF5 award, replay and cold return, orphan-account
history refusal, historical/missing/excluded/duplicate clear filtering,
full bag, encoder failure and lease revocation rollback. The original99
committed-clear run and all earlier failures remain separate evidence;
the successful continuation executes only one new clear. Item304 proof
is a static same-client record plus reviewed codec roundtrip, with a finite
single-instance source cap; it does not claim native execution or a global
native stack maximum. No account/player database, credential, log or test
fixture is included in this commit.

Two source-scope tables initialize lazily only on qualified acceptance.
Existing rows are not migrated, merged or erased. Read-compatible recovery
must retain all eight leaves with source mutations disabled; a pure old
parent rollback cannot safely read newly saved53520/712413 state. Player
databases are never rolled back.

No page use, new-page point budget, selection policy, retail SKU or price,
Preset default records, client UI/effects/timers, SDK or game control is added.
Controlled clear witnesses are not natural100-dungeon or GUI acceptance.
This source preparation does not by itself assert formal installation;
deployment and public eligibility verification require their independent
maintainer acceptance records.
