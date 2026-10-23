# Reject mailbox mutations from pending or finalized characters

An authenticated role scheduled for deletion can retain its old town connection and still send, mark read, claim, delete, add a blacklist entry or remove one. Existing account/UID checks do not include saved lifecycle state.

Require active lifecycle eligibility inside each existing mutation transaction before old-receipt lookup or writes. Preserve MailError/native failure responses and all current mail recipient scope rules. Read-only inbox/status/blacklist, GM issuance and internal expiry/return maintenance keep their existing behavior.

Scope: game_mail, player_mail and mailbox_extras only. Reuse existing formal lifecycle.states without depending on the separate item_actor repair. No client, schema or protocol changes.

Delivered online and independently locally in `items-economy-pending-actor-20261021-v1` after dual SQLite API/code/configuration backups, normal server drain and separate120-second observations. Actual accepted full file SHA and owned read-only public selection/town and bank26A/54F compatibility verified; negative lifecycle/restore/replay evidence is private SQL/TLS, not public exploit injection or GUI acceptance. No client, schema, credentials, player databases or runtime resources added.

Two portable SQL test methods passed in collaboration context with SHA-locked read-only resources. Source CI and repository guard must pass before submission; full runtime CI without assets remains separate. Other catalogue and natural player-flow gaps remain pending.
