# Current selected title in native snapshots

An owned character's sanitized selected title was omitted from both native
character and dungeon member snapshots. Both encoders retained their fixture
value zero. Separate title notifications did not establish that the identity
survived every snapshot and native refresh.

Issue #544 carries the current selected ID in the existing character field
`0x307` and member field `0x3ef`. Unknown, invalid or ineligible IDs reject.
Existing SQL projection continues to validate ownership and expiry. No title
stats are added to naked inputs: title options, equipment and final calculations
remain native client behavior.

Validation:

- Six complete original-reader DTO cases cover selected/no-title character,
  roster and member encoding; eight invalid cases reject. No-title and legacy
  callers retain their bytes.
- A disposable owned native role preserved the selected title through two
  weapon moves and a new client process, with matching original complete power
  results after rewear and cold login. Item instances and balances were retained.
  No power cache setter, physical input, player process or production database
  was used in this qualification.
- The public encoding functions match the qualified formal candidate. Existing
  formal fatigue and Hero-mode differences outside this change remain bound
  separately; this PR neither imports their missing public dependencies nor
  removes them from the formal candidate.

This is a two-file protocol change with no schema, ownership grant, client
resource or new runtime hook. Deployment is separate from Git merge. Full
natural combat, multiplayer damage and the separate power cache lifecycle are
outside this acceptance; private graphical dungeon entry remains unqualified.
