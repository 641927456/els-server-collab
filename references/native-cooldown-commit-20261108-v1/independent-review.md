# Independent review: cooldown commit observer

Root reviewed the four-file candidate authored by chat 01a1b820, independently of that author's implementation and verification. Recommendation: accept the pinned source for signed delivery; actual upgrade/load and natural gameplay remain separate acceptance boundaries. This technical review is not GitHub approval.

## Scope and risk

Large repository, surgical review of five support leaves (four product changes plus required compatibility hashes). Native instrumentation has high availability impact. No unresolved critical/high/medium/low code findings were identified in this diff. One deployment acceptance gap remains: the fixed component has not yet been loaded through the formal signed upgrade. Natural gameplay is not established by the host fixture.

## Confirmed cause

The actual 06:28:24 HKT run contains twelve errors at composed script10.js:799, mapping to the old dungeon_result_stats.js:55. Cache readiness predates the errors. The old common join reads a node from RBP+30 even when native branches 8F4B63, 8F4B88 or 8F4BCA skip pair initialization and insert/find. The wrapper's generic script-error callback sets native_cache_failure, emits a misleading cache message, raises, and its existing finally cleanup terminates the owned game. The exact one of the three skip predicates was not recorded. No historical Windows native fatal is substituted for this run.

## Changed paths and adversarial cases

Candidate dungeon_result_stats.js:38 creates a per-invocation false marker. Lines 53-55 consume a successful marker before any node read. Lines 68-73 arm it only at 8F4C19, immediately after the original insert/find call. The existing-key native add remains before the 8F4C2D observation. Owner, main-thread, tree, UID and game generation checks remain. Nested remote frames cannot arm an outer frame; a skipped iteration after success cannot reuse its previous node. Frames are removed on leave and all hooks on dispose. No lock, crypto, economy, protocol validation or player-data semantics change.

The new 16-byte pin covers the actual unmodified instruction window; real Gum host verification includes both marker and join attachments. Root independently disassembled the fixed snapshot and checked all four incoming acceleration edges. The other (discrete) commit site always follows initialized pair storage and insert/find; it has no analogous skip edge.

probe_updated_client.py:259-263 now classifies generic composed-script errors separately; :270-272 preserves explicit failure and cleanup. Real cache-specific events remain cache failures. Errors are not swallowed. launch_client.py:225 uses the existing interpreter with -X utf8; launcher UTF-8 readers and the nested child's actual Chinese output were checked by the author's exact-source test.

## History and reach

Git blame on references/native-shared-sender-20261108-v2/candidate/tools/probe_updated_client.py:259-261 identifies retained callback behavior in 5b8b7530a (PR951). Its direct report-script source was not archived as a tracked leaf in that commit, so native observer history is established by installed V108/V109 SHA manifests rather than fabricated Git blame. Four parent hashes match both actual V108 and actual V109. Root verified all 71 direct tools Python/JS sources match, permitting reuse of the successful composed-source and lifecycle tests. One install call and two compose layers reach this observer; one composed-script callback routes all generic script errors, and one shared make_command entry serves both local and online launch modes.

## Validation

review-bindings.json pins candidate, test sources, dependencies, source archive and three successful result files. Six new skip/marker/generation groups and ten existing report/PvP/writer/lifecycle groups passed. The actual Frida 17.23.3 host executes original skip/join instructions: parent source produces four invalid-address errors; candidate produces zero, retains native inserted/existing-key values, and records totals 1.5 then 1.75. Both owned helper processes exited. This is a synthetic native host, not a natural battle. Root reused these exact-input successes and independently checked source, disassembly, actual trace and parent hashes. Required profile artifact hashes were updated without changing policy.

## Remaining investigation

5BF: no occurrence in the retained roughly eight-hour scan; the older occurrence is attributable to an owned QA enrollment but its cursor payload was not retained. No relaxation of the legitimate zero-cursor requirement is justified.

Repeated sequence: four retained cases precede V108. Two captured comparisons prove different authenticated bodies/plaintexts reuse a counter, excluding an identical adjacent packet replay. The historical producing thread/context was not captured. No post-V108 recurrence is present in the scanned window; this does not establish a permanent absence.

Five Windows frida-agent.dll faults from older runs were matched by exact PID and creation time to isolated QA. Registers/stack dumps are unavailable, so the release-site read alone does not prove their exact lifetime cause. The separate recorded connection-queue delay is not bundled into this client patch.
