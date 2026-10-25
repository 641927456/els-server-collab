# Accepted local source refresh

At source commit `cc073577789cf222ee6c99d5a92e7285794e9f75`, the root Python/JSON source matches the accepted
`local-native-battle-special-elixirs-20261025-v1` runtime. This includes the
later PvE economy, life potions, teacher containers and special-elixir changes.
Its new historical source index is
`channels/local-native-battle-special-elixirs-20261025-v1.json`.

The original V38 immutable common baseline, its source index and
`channels/active.json` are preserved. They remain V38's three-way merge base;
this change does not pretend that the historical Silver release is current.
Updates remain explicit and fast-forward-only. Already installed identical
source needs no business-file replacement; newer local edits remain protected
by the existing merge and conflict checks.

Only accepted Python/JSON source and source metadata are synchronized. No live
configuration, credentials, databases, saves, clients or runtime binaries are
included. No server is restarted or reinstalled by this Git operation.
The paired online source and its intentional differences are archived separately
on the collaboration main branch under issue #497.

The subsequent accepted `local-boss13100-native-resistance-20261026-v1`
source adds only three existing `raid_npc_stats` revisions. Its separate
historical source index preserves the earlier source commit and index.
