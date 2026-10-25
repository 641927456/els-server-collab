# V38 accepted local source channel

The collaboration main tree is a source review view and is not a complete current standalone runtime. V38 source updates must use this accepted local source channel, not overwrite the local runtime with main.

`updates/local-v38` contains the exact Python/JSON leaves of the already installed and accepted local release. Its immutable bootstrap branch and full SHA-256 source index are recorded in `channels/active.json`. No clients, Python runtime, static binary assets, live configuration, credentials, databases or saves are uploaded. Existing runtime dependencies and the local server configuration are retained by V38.

The current business code is already installed locally. This real update exercise verifies Git fast-forward from the older main source view, native V38 preflight, automatic SQLite API backups, runtime installation and at least 120 seconds of observation. It does not imply a new business feature or natural gameplay test. The EXE is unchanged.

Future commits to this channel must be fast-forward additions of qualified local source with full indices and acceptance evidence. Do not force-push it, publish test fixtures here, or treat Git publication as server deployment. The user still explicitly starts the native one-click update, which performs its own validation, two locks, backups and protected installation. Source conflicts or a moving local parent fail closed.
