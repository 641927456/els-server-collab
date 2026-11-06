# Maintenance admission differential review — C16 → C18

Author security review; this is not GitHub human approval or deployment acceptance.

## Result

| Severity | Findings |
|---|---:|
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Low | 0 |

The change is HIGH priority for review because it touches authentication. No demonstrated authentication bypass or economic regression was found. Recommendation: retain the candidate for delivery, subject to the existing exact-head Git approval and actual production acceptance. One changed source file was reviewed in full, including the original registry, native/relay dispatch, TLS and error boundaries.

## Pinned baseline and scope

Baseline C16 manifest `7cc4800fb77d3d04702291b53b7fee29b3de848e0f7aa4a3f9bde819572fcc8b`; candidate C18 manifest `b45e5e1fa5c0ecf6d86e702cf2278bbb152e3919fdee16178f39cdc7e0547b5c`. Transport SHA: afb294eabb3fbbc9784b2718b02bccfaaa61371ff039ad83d67873b5349ea714 → eaef391376451c526857472e0e90c3837a55f041a4ab947108c528420da99007. The normalized source change adds 27 lines and removes 0 lines. The archived parent transport in `refs/unified-latency-capacity-20261106-v3` is byte-identical to C16; its authentication lines were inspected with git blame at worktree head `45642936a0b9486cb49690546a8105515626df88`. These are SHA-pinned release trees, so Git attribution describes the archive commit rather than claiming original logical authorship.

`maintenance-entry-unchanged-business-contract.json` removes only the declared startup fields, two admission helpers, their two call sites and the json import, then compares the entire remaining module AST to C16. The complete original authentication, TLS, native request loop, financial callbacks, commit-before-ACK, ownership/lifecycle guards and close path are exact. The 15 ms Town clock, 250 ms background checkpoint, FULL/WAL/automatic1000 and normal foreground priorities remain unchanged.

## Entry points and blast radius

`GameServer.start` loads a publisher-owned `maintenance-admission.json` beside this deployment's private accounts file before opening a game listener (transport line43). The loader begins at line60. `_check_maintenance_admission` begins at line73 and has exactly one call site, line138, immediately after the original live registry authentication. The startup loader likewise has one call site. The transitive scope is every newly authenticated native or relay connection. Account gateway/diagnostic operations do not create a native game session and remain on their original paths. Existing game packets never call the gate. No LOCAL-specific auth branch, player permission result cache, financial mutation, new public management API or new thread is introduced.

The allowed ID set is immutable operator startup input. It does not replace current credential or enabled-account checks. Policy removal is the explicit publication action that opens this already-running server; a later maintenance session requires a fresh normal server start with its policy present. File contents are not a supported live policy-edit API. The publisher must create the complete private policy before starting the game, keep its ownership and contents stable during QA, and remove only that exact owned file after successful QA and account cleanup. Deployment code must enforce that ownership; it has not yet been executed.

## Adversarial checks

A remote player with a valid ordinary token cannot select an allowed account ID in the wire request: the ID comes from the unchanged registry. A known valid ordinary account and its relay are denied under maintenance. An invalid token and a disabled allowlisted identity are denied by the original registry. The file is operator state in the private account directory, not writable through the game admission protocol. An administrator able to delete it already controls the account data and server; removal is an intentional operational transition, not a substitute for player credentials.

The presence check uses stat and catches only FileNotFoundError. Permission and I/O errors do not silently open admission. An invalid policy fails before binding a listener and uses the existing start cleanup. Existing native requests do not read this file, and after opening admission subsequent authentications do not read it either. There are no removed security checks or new callback execution paths.

## Actual validation and limits

The real Python3.14t TLS/native test passes: allowed role reaches Town; valid ordinary native/relay denied; bad token and disabled allowed identity denied; existing native request succeeds with gate stat forced to fail; direct permission failure does not clear maintenance; malformed startup produces no listener; removing the policy opens the same server; subsequent normal authentication requires no policy-file reads. GIL remains disabled; own runtime, connections and workers retire normally. The first test fixture attempted to read playing before native selection; that failed fixture and its clean retirement are preserved, and the UID lookup was corrected to the existing Characters reader.

C18 imports all111 frozen overrides from their exact origins with GILfalse. The actual packaged v15 interpreter completes ordinary native Town, dungeon, death and glass paths with 250ms/background-4 checkpoint and normal thread join. Compiled signed selection and endpoint acceptance are separate delivery checks and must be recorded when finished. Production installation and production gate activation are not claimed here.

The human shortened capacity acceptance to300seconds. C16's full20actor mixed run passed all server, WAN steady/burst, SQL, financial ACK, accounting, source and cleanup targets. This evidence is reused for C18's AST-identical steady gameplay; new admission behavior is separately tested. No one-hour qualification, natural GUI/AOE qualification or arbitrary50-player capacity is claimed. The22/24actor failures and user-cancelled hour remain failed/unqualified evidence.
