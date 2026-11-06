# First pickup economy catalog prewarm

Addresses #825. The first coin reward previously loaded the collection/synergy economy catalog inside the write transaction. Its validation parsed two SHA-pinned option JSON files totaling36,106,820 bytes and70,522 rows. Subsequent requests used process caches.

The three-line Application.start delta loads the existing immutable catalog during static initialization, before constructing player accounts or opening writers/listeners. Player entitlements, bonus calculations, debit/grant receipts and transactions are unchanged.

Actual candidate startup test: catalog cached before admission; first native owned pet pickup23.4ms, then12.9/13.0ms with cold balances verified. Original first pickup217.2ms in the same isolated fixture. Invalid catalog stops startup before account construction or database creation. These are local results, not production or natural GUI claims.

`source/` and `base/` retain exact runtime input/output bytes bound by `source-manifest.json`. Main's active server tree differs from the installed ONLINE baseline, so this archive submits the qualified delta without replacing that separate tree or bundling unrelated dependencies. Full TLS test sources require the project's pinned private runtime and existing reference fixtures. No databases, credentials, raw captures or runtime logs are included.

Portable integrity check:

```powershell
python -B refs/native-first-pickup-prewarm-20261104-v1/verify_archive.py
```

ONLINE installation is recorded separately after actual acceptance. No LOCAL, launcher, client, configuration or schema delta.
