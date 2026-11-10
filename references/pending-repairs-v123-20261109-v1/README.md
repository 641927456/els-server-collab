# V123 qualified repairs and installed support source archive

This package contains two Gold Castle server repairs and the exact ten support source files already installed by V118–V121 and retained by V122. It is a source submission, not an instruction to replace the repository's older root modules or copy individual files into a running server.

The parent title-integrity repair is [PR 969](https://github.com/641927456/els-server-collab/pull/969), commit `ab4461f4f8854957b523a7106f0af0109c136c96`. Its separate `title-integrity-v122-20261109-v1` archive contains the three title repair sources, including the profile; it need not already exist on this submission's branch. This package addresses [issue 970](https://github.com/641927456/els-server-collab/issues/970) and does not merge unrelated open PRs or the unfinished Shadow Castle candidate.

## Two server repairs

- `apple_consumables.py` admits ordinary solo Gold Castle stage sessions through the existing consumable readiness check. The prior blanket encounter rejection produced the error response even when the session met all ordinary conditions. Session ownership, current lease, stage loading, identity, reward and clock checks remain in place; other special encounter kinds are still rejected.
- `dungeon_routes.py` keeps the original Gold Castle hub controller roster after returning from an exhibition wing. Removing completed-wing controllers had made the native condition scan repeatedly request a transition that the server refused. The boss gate now accepts completion of any one exhibition wing, while retaining the original controller-retirement requirement and refusal of already completed destinations.

These follow the existing verified Gold Castle rule and original condition handling. No new reward, item pool, probability, map geometry, client resource or database migration is included. Official rule references retained from the original review: [Gold Castle introduction](https://els.ztgame.com/html/news/134b2ae/000-1693-016c8-365926.shtml) and [Monaterra dungeon information](https://els.ztgame.com/game/00a-1693-00389-384026.shtml?mt=903).

## Source layout and parent contract

- `source/els_server/domain/` contains the exact two qualified candidate leaves. `baseline/` contains their exact installed parent leaves for negative regressions.
- `source/tools/` fills the previously missing source archive for ten installed support leaves: result statistics; shortcut and challenge instruction probes; launcher process guard; cache-operation context, fault metadata and diagnostic collection. These bytes are unchanged from the signed V122 runtime. Archiving them does not claim that these changes cured all crashes or that every memory write can be identified from a log.
- `source-contract.json` binds each file by size and SHA-256, lists the twelve tested server dependency identities and records hashes of the original private validation receipts. It does not embed private receipts or claim that a receipt hash makes a private fixture publicly replayable.
- `launcher-source/` contains exactly the three changed inputs from the actual V123 private build: `AutoUpdate.cs`, `UIScrollRuntimeCohort.cs` and the signed runtime manifest. `launcher-build-contract.json` records all 146 compiled input hashes and 101 resource mappings; the other 143 inherited input bytes are not duplicated. The actual build inputs were all hashed and compared to V122, confirming only those three changes. This reference package is not a complete standalone server or launcher build. Signed components must be selected together with their matching profile and dependencies through the normal updater.

No player databases, credentials, raw packets, crash dumps, runtime traces or client binaries are included. Existing generic default client paths and the fixed public launch argument are preserved as source constants so source identities stay exact. The signed manifest retains its existing build-origin path metadata; its signed bytes cannot be redacted.

## Portable checks and reused evidence

From the repository root:

```text
python -B references/pending-repairs-v123-20261109-v1/verify.py
```

The standard-library-only verifier checks all fourteen source identities and Python syntax, the three archived launcher inputs, their full inventory/resource contract and signed-envelope SHA/payload bindings, then executes eight tests against the actual production predicate ASTs. It does not independently verify the RSA signature. Synthetic collaborators exercise the Gold Castle admission failure in the old source, unchanged session/clock/ownership guards, each single-wing boss admission, original actor retirement and completed-destination refusal. The fixture does not load a client catalog, create a database or start a service.

The full original isolated TLS consumable/transition checks and three first-wing plus optional-wing condition replays passed earlier and are reused because their source and twelve declared parent dependencies match. The combined leaves additionally passed 39 in-memory assertions, including the returned hub roster and readiness at stage boundaries. These checks are referenced by sanitized receipt hashes rather than copied private inputs. The portable predicate tests do not independently recreate that full roster/transaction/native-consumer validation.

Historical support regressions and the V121 diagnostic collection checks are likewise referenced with explicit per-version scope. A prior version's receipt is not a claim that its entire suite ran against every later extension of a file. No TLS, native, game or performance test is repeated for this source archive. Natural complete gameplay and game stability remain outside these checks.

## Delivery status at source preparation

The V123 private build completed with launcher SHA-256 `420357d716c56c8098fcb71e9ce30b63d1cd87c577d095cfc0e03ec1c5bdf524` and runtime SHA-256 `cec75a0e994ac4d6b0c64f4d755f690455f42ab4017671da3e0c0ed8caaf2625`. The controlled private component upgrade passed: all 2,896 selected files matched, two files were downloaded, 2,894 were reused, and the repeat selection downloaded zero. No game was started and the installed current pointer was unchanged. This private check did not exercise an anonymous public download or the actual old-launcher updater.

At this source freeze, public release and production installation had not completed. The release owner records those later delivery results separately and updates the PR; these frozen source identities remain unchanged. Natural gameplay is unverified.
