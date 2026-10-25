# Accepted runtime source coverage

The accepted online and local `native-battle-special-elixirs-20261025-v1`
releases contain the same latest delivered feature batch. Local activity GM,
mode guards and launcher support remain local; authenticated coupon issuance
and redemption remain online. Different file totals do not identify a newer
business version.

`references/accepted-runtime-20261026-v1/manifest.json` records the exact
already accepted Python/JSON source for both channels. Equal bytes are stored
once under `shared/`; channel variants remain under `local/` and `online/`.
It includes the later PvE economy, life-potion, teacher-container and special
elixir revisions absent from the older registered source baseline.

Run `python -B tools/verify_accepted_runtime_sources_20261026.py` to verify all
source hashes, sizes, Python syntax and JSON parsing. The verifier also accepts
`--local-source-root PATH` for an independently checked local-update checkout.
No game or database is opened by this command.

The dedicated `updates/local-v38` source channel is refreshed separately.
Its original accepted baseline and immutable source index remain intact for
V38's three-way merge; a new historical index identifies this accepted source.
The updater still requires an explicit user action, preserves newer local
changes, rejects conflicts and backs up saves before installation.

This is source synchronization, with zero new gameplay changes and zero server
deployment. Existing runtime transaction, public QA and 120-second acceptance
evidence is reused through exact source equivalence. Natural GUI/combat is not
claimed. Player/account databases, credentials, private live configuration,
runtime binaries and game-client files are excluded. Required runtime resources
are identified by hash only; this archive is not a standalone runtime package.

V37/V38 launcher-source work and third-party PR #487 belong to their existing
authors and are not included in this change. See issue #497.
