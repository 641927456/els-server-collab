# Reject pending or deleted actors before decomposition and ordinary cube/ice transactions

A character scheduled for deletion can retain its earlier town session. Ordinary decomposition, fixed/selected cube opening and the existing local-policy ice draw can then commit against that character. Their storage transactions do not check the saved lifecycle before new mutations or committed receipt replay.

Reuse the pending-item-actor helper from the separately merged dependency. Apply one guard per transaction immediately after BEGIN IMMEDIATE. Preserve original reward rules, prices, local ice weights, receipts, protocol failure responses and legacy saves without lifecycle tables. Event-specific delegated cube transactions are outside this change.

Delivered online and independently locally in `items-economy-pending-actor-20261021-v1` after dual SQLite API/code/configuration backups, normal server drain and separate120-second observations. Actual accepted full file SHA and owned read-only public selection/town and bank26A/54F compatibility verified; negative lifecycle/restore/replay evidence is private SQL/TLS, not public exploit injection or GUI acceptance. No client, schema, credentials, player databases or runtime resources added.

Two portable SQL test methods passed in collaboration context with SHA-locked read-only resources. Source CI and repository guard must pass before submission; full runtime CI without assets remains separate. Other catalogue and natural player-flow gaps remain pending.
