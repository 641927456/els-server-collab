# V122 title integrity repair

V121 changed the second option of title 12360 from 87018 to the approved 100003019 without updating the native registered-object checksum. V122 calls the existing native refresh operation immediately after that write, in the same initialization callback and for the same resolved object. The approved effect remains unchanged.

The dump and matching loaded source linked this stale checksum to delayed undersized allocation: a 2,176-byte resource read received a 2,048-byte payload bucket and the reader still wrote the full resource. The later heap failure detected the earlier damage. The exact captured object checksum matched again when only the changed option was restored offline. This identifies this captured failure chain; it does not establish the cause of every earlier TLS fault or hang.

## Source and delivery scope

- `tools/` contains the exact three support files delivered by V122. JavaScript invokes the existing native checksum refresh at RVA 0x36d720 using its uint8/AL result. A rejected return restores this write and throws; native exceptions propagate. Python composition pins the relevant native instructions. The 60-entry compatibility profile changes only the two title-source bindings relative to V121.
- `tests/fixtures/` preserves the exact V121 baseline for the negative regression. It is test input, not a deployable component.
- `launcher-source/` contains exactly the three changed V122 build inputs: the version constant, selected signed payload hash and signed manifest. `installation.json` records all 146 compiled input hashes and resource mappings. The other 143 parent inputs and the external icon are not included, so this package alone is not a complete launcher rebuild. This submission does not claim to merge their inherited implementation.
- The profile is an exact snapshot of the released runtime parent plus this fix. It does not replace the repository's older root profile or historical archives. Installation remains through the signed launcher update, not by copying this reference directory into an older runtime.

No original game EXE/KOM, server business logic, allocator behavior or protection switch changes are part of this repair. No new hook is introduced. Dumps, raw runtime logs, player databases and signing secrets remain outside this repository. The unchanged signed manifest includes its existing build-origin metadata; its bytes must remain intact for verification.

## Verification

Run from the repository root with Python 3 and Node.js available:

```text
python -B references/title-integrity-v122-20261109-v1/verify.py
```

The portable checks execute 26 cases against the actual JavaScript, including the stale-checksum baseline failure, refresh ABI, success, rollback, native exceptions and identity/object guards. They also validate the exact source hashes, profile delta and real Python composition using synthetic instruction bytes. This test is included in source CI and requires no game, private snapshot or server.

The released bytes additionally passed three offline native-instruction cases, actual-parent composition, signed component selection and the actual V121 updater path. The update downloaded three files and reused 2,893; a repeated update downloaded zero files. These completed checks are reused because the release bytes are unchanged. Natural gameplay stability and execution of the native effect in a live game remain unverified.

## Player update

[V122 release](https://github.com/641927456/els-launcher-updates/releases/tag/launcher-v122-f4b95542297e9c85) is already public. The launcher uses the [latest signed metadata](https://github.com/641927456/els-launcher-updates/releases/latest/download/latest.json). Its signature, EXE identity and all 61 runtime asset records were checked against the delivered build. This source submission does not republish or increment that version.
