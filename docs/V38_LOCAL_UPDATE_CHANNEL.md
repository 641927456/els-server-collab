# V38 accepted local source channel

The collaboration main tree is a source review view, not the current standalone runtime. The exact published V38 executable expects a verified historical local baseline and full source SHA-256 index before its native one-click installer can proceed.

Use the `updates/local-v38` branch in a separate clean source checkout. Its initial immutable baseline is `snapshot/local-v38-accepted-20261025-v1`, commit `1eba786c893c9c405cfa0523340f875c55ca519a`; initial update commit `19edffa0605190dcca288050249e1c0a1f7c0071` supplies the channel metadata required by V38. The 883 eligible Python/JSON blobs are bound to the already accepted `local-silver-mirror-completion-20261025-v1` local manifest `f787808be4221876a147674b5504ef88f43da079580fc95a5ad1bf21a2dce215`. Its previous local acceptance observed 121 seconds. All 698 Python sources compile and all source files pass the private-state/credential guard.

No client, runtime binary asset, live server.toml, credential, database or save is exported. The main code tree and main channel selectors are unchanged. The source branch is an accepted local channel, not a synthetic test fixture. Git publication itself does not deploy any service.

The published V38 EXE remains SHA-256 `0593fbec73b409cd02d368b2dda186fbdf5164c2d8d665c713af50acd7828093`. Its native button fast-forwards Git, checks the actual local parent and retained client dependencies, uses database copies for preflight, obtains the common exclusive two locks, makes SQLite API backups of the actual account/save databases, installs an immutable runtime and observes it for at least 120 seconds. Failures preserve the existing runtime; database backups are never automatically restored over player data.

The current local business code was already accepted and installed before this channel was added. A successful first real installation can therefore have zero business-file changes while still proving real Git pull, backup and runtime promotion. Do not call that a new gameplay feature or natural gameplay acceptance.

Future channel updates must fast-forward qualified accepted local source and preserve its complete SHA index and acceptance evidence. Do not force-push, publish test fixtures here, copy a collaboration main tree over the local runtime, or treat a test result as player acceptance. The native installer still checks every actual parent and protects newer local changes.
