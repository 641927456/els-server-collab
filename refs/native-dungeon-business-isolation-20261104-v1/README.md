# Dungeon business isolation ONLINE source delta

Addresses #823. Loaded dungeon consumables, pickup, doors, clear, native skill producers and settlement use a dedicated route, and dungeon requests receive priority over queued town work. Existing authentication, economic consumers, transaction receipts, party barriers and realtime combat consumers remain authoritative.

`source/` contains the seven exact runtime leaves. `base/` contains the five existing comparison inputs; the two new modules have no prior leaf. `source-manifest.json` binds every source byte and inherited queue dependency. The deployment parent is `native-teacher-potion-count1-20261104-v1`; its seven relevant inputs match the earlier comparison parent exactly.

Main's active `els_server/` tree is older and lacks the deployed economy worker infrastructure. This archive preserves the reviewed runtime change without overwriting main's distinct implementation or importing unrelated pending runtime dependencies. It is an exact source submission, not a main runtime activation or merge approval.

Validation: 38 related checks passed; see `validation.json` and `review.md`. Natural GUI, natural battle, all character skill families and production load remain unverified. Test sources are retained without databases, credentials, captures or raw logs. Full TLS fixtures require the project's pinned private runtime/reference resources and existing analysis helpers; they are not a standalone public distribution.

Run the portable source and scheduler checks from any checkout:

```powershell
python -B refs/native-dungeon-business-isolation-20261104-v1/verify_archive.py
python -B refs/native-dungeon-business-isolation-20261104-v1/verify_scheduling.py
```

Delivery status is recorded separately after actual ONLINE acceptance. This source archive changes no LOCAL or launcher files.
