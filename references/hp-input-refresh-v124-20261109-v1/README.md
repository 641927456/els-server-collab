# Repair HP input refresh before the original Actor refresh

This independent repair contains the changed `native_cache_sync.js` and its single compatibility artifact binding against V123. The existing 250 ms budget now applies only while the Actor's seven base inputs still match the active Unit side. A world-buff profile overwrite triggers the existing native producer before the original Actor refresh can clamp current HP against a transient lower maximum. Stable frames retain their budget; injured players are not healed; genuine maximum reductions still clamp. LuCiel active/fallback side selection is retained. No hook, native-call signature or runtime module is added.

The profile changes only the `native_cache_sync.js` SHA. The other 59 artifacts, native contract and original-client/resource bindings are unchanged. Original EXE/KOM, ordinary monster HP and buff values are not changed. The separate scene-retirement repair is not included in this source PR; both may share the V124 deployment receipt.

Prior support-source provenance is [PR971](https://github.com/641927456/els-server-collab/pull/971), head `351f61ac5ebe803b97e53b7882e3bd3f9456f7d4`. This package does not claim that PR is merged or repeat its unrelated business sources.

Run `python verify.py` from this directory to check exact source identities, the single profile change and the launcher input contract, then run the Node regression. Node is mandatory. `python verify.py --identity-only` checks archive identities without executing behavior.

The V124 private build adds three archived launcher inputs under `launcher-source`: `AutoUpdate.cs`, `UIScrollRuntimeCohort.cs` and the signed component definition. `launcher-build-contract.json` records all 146 input hashes and 101 resource mappings, retaining the other 143 inputs by parent reference. The package contains no launcher executable or runtime archive. `tests/verify_launcher_inputs.py` checks the three actual source files, their resource identities, version/cohort/profile binding and the signed payload's three runtime changes: one server leaf and two support leaves, with 2,893 of 2,896 runtime leaves preserved. It does not independently verify RSA or execute the launcher.

The common signed definition also references the separately tracked [scene-retirement issue 973](https://github.com/641927456/els-server-collab/issues/973). That server source remains in its own archive/PR, rather than being copied into this [HP issue 972](https://github.com/641927456/els-server-collab/issues/972). The recorded private build is not a public-release, upgrade or installation receipt.

`tests/test_attribute_refresh.cjs` retains the prior test's real scheduler/ability functions and observable native-call substitutes. Its small baseline fixture contains the two relevant functions from the unchanged parent plus extraction delimiters. It reproduces the original transient HP clamp and checks repeated overwrites, injured HP, stable-frame budgeting, actual equipment reductions and LuCiel sides. It does not execute native game code.

`evidence/reused-results.json` preserves the prior six-group Node result and private matched-image composition result by bounded values and hashes. Source packaging does not repeat those successful tests. Test-file hashes observed during packaging are not retroactive proof of their identities at the earlier execution. The composition's private executable image is not distributed.

This source archive does not establish signing, installation, native gameplay, natural GUI acceptance, stability or a general crash fix. The release owner records those separately. No player data, credentials, raw packets, runtime logs or dumps are included.
