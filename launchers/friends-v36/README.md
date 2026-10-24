# V36 unified launcher source archive

This records the already delivered V36 unified launcher. Local and friends modes
share the same native application, `MainForm.LoginAndStart`,
`tools/launch_client.py`, and `tools/probe_updated_client.py`. The old launch
entries forward to that core. Local GM/save isolation, online TLS authentication,
DPAPI credential protection, signed updater and mode-preserving restart remain.

Only four changed native source files are copied here. `source-lock.json` pins
the other six C# files, `app.manifest`, and the external asset lock in the
preserved `launchers/friends-v35` directory at the fixed source parent. It also
records the original V36 source freeze and each archive leaf's provenance.
`runtime-support/tools` holds the five exact changed friends runtime source
leaves. `runtime-support/local` holds the distinct local profile and four local
manager source leaves from the immutable local delivery manifest. The unchanged
V35 resource support leaves are referenced by exact repository path and SHA.
These versioned bytes must not replace root tools or the standalone branch.

`build.py --assets ELS-V29-Build-Assets.zip --output <new-file.exe>` is an optional
compiler entry using the locked external image/icon assets. It compiles all ten
original V36 C# units plus the delivered signed public runtime member manifest.
It does not sign, generate a payload, publish, install, or claim a byte-identical
historical EXE. No build was performed for this archive.

Binary assets, executable/ZIP payloads, client EXE/KOM, databases, owner/account
configuration, credential stores, logs and signing private keys are excluded.
The signed member list contains only public file names, hashes and a public
signature. Inherited public product endpoint/pin literals remain in source.

The fixed client and resource fingerprints are the witnessed compatibility
profile, not a claim of the latest official client version. Existing V36 formal
local/friends preflight, changed-core refusal, hidden UI, password and signed
update acceptance receipts are reused. The first publication's stale-V35
fixture failure and its recovery remain in the evidence record. Natural player
login and multiplayer acceptance are not inferred.

`release.json` binds immutable V36 source, signed runtime manifest, local
delivery manifest and actual historical delivery receipts. The captured launcher
pointer SHA identifies an immutable old observation; it is not a new live
current or a safe terminal state for the ongoing server release queue. Git does
not deploy, activate selectors, or modify any current pointer. V35 and all other
source tree entries remain preserved.
