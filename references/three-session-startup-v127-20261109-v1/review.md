# Differential review — V127

## Executive Summary

| Severity | Findings |
|---|---:|
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Low | 0 |

Risk: MEDIUM because native allocation and startup ordering change. Recommendation: accept for controlled signed delivery with the stated gameplay boundary. This is a technical review, not GitHub approval. Reviewed 14/14 runtime differences plus Program.cs; runtime diff +171/-27 lines.

## What Changed

Immediate baseline is SHA-pinned V126 signed payload. All engine parents and startup parents match their authors' tested input. Online has three older support hashes; deployment binds those separately. V126 18R source is unchanged and retained through dependency PR979. No new authentication, economics, migration or account fields.

## Critical Findings

No demonstrated security defect. The original two native resource candidates would independently attach to the same loader and invalidate each other's entry pins. Integration resolves this by using one unchanged peer-authored Shadow Castle listener and a disjoint union of 18 castle plus one Lithia hash rows. No second Hook or generalized scanner is added.

## Analysis and Blast Radius

- npc_initialization has six direct call sites across static dungeon admission, dynamic spawns, hunter chest, field boss and pet battle. class_id/is_npc now come from the pinned authoritative catalog; all 4555 template and 18 native branch results are reused with exact source SHA. The admitted-map evidence covers 37 maps/170 stages.
- stage_platforms has one caller, after existing B3 load synchronization; graph identity and dungeon 34800 bind the triggers. Five-room regression and representative party barriers pass. It changes no reward/ownership path.
- member is shared by dungeon/start, field/PvP/duel/mount/photo/story consumers. Its ERP value comes from the existing server snapshot and resonance.wire validates type, level/curve and locked state. Fourteen current native FullUser/14A decoder and actor-copy cases pass, including 64-bit XP, locked state, solo and party.
- Native loader attaches once at RVA3933FE0, with entry and tail pins from the fixed runtime SHA. It selects exact size+SHA, allocates a per-call private buffer retained through onLeave, verifies output SHA and native success. Nineteen inputs repeated twice, wrong SHA, native-failure and wrong entry cases pass. No game file write. Calls without a signed resource match retain their original arguments.
- read_session is opt-in synchronous thread-local scope, with one production use around inventory-policy module initialization. Finally closes its connection; nesting and thread/exception fixtures pass. No player database connection changed.
- Digest cache is per-attempt and shared across resource preparation only. Stat changes invalidate or fail; no persistent trust or learned hash. Four fixtures pass. Full signed profile and native witnesses remain required.
- Program.cs removes duplicate standalone check. launch_client still runs compatibility_preflight, ensure_unchanged and the original native probe before process creation. Explicit --check stays available. Three wrapper fixtures reject unsupported clients before game start. Session credential lifecycle is unchanged.

## Historical Context

Git base8619b3a4 and PR979 head2aed4183 are preserved. Git blame of the removed duplicate Program preflight points to e2cc9a580 (2026-11-06), exact archived parent Program SHA319805b3. Release-tree files are outside Git; pinned parent hashes and author result records provide the immediate history rather than falsely attributing old checkout lines.

## Adversarial Checks and Tests

Modified/unrecognized archives fail original hash gates; same-size unrelated bytecode cannot select a repair. Wrong native entry bytes prevent installation. Corrupt transformed buffers fail updated SHA. Resource data must be signed through the same profile. No client-provided amount, role ID, lease or reward input added. Server auth and committed receipt/transaction paths are untouched.

The integrator independently reviewed other chats' unchanged Hook implementation and resource edits. Startup optimization and union-data wiring are self-reviewed here; that label does not claim independent authorship. Combined tests use the exact candidate runtime; unchanged prior tests are reused. Natural GUI battle, full-route clears, PvP and every transitive UI consumer were not replayed. No full security audit is claimed.

## Recommendation and Limits

Proceed with exact signed/source hashes, actual old-updater selection, original client compatibility, owned startup/native-readiness and dual-backend observation. Keep source submission separate from main approval. No blocker found in reviewed scope.

## Authorized Quick Start addition

Reviewed all three added peer files against V126 parent hashes. LocalSession parses options578 once through existing quick_start.selected and reuses that boolean for storage and ACK. Transactional pre-encoding uses the same value. The keyword default remains false for ordinary creation and error replies; identity, ownership, sequence replay and starter qualification paths are preserved. create_ack has three runtime callers (success, error and transaction pre-encode). No new input parsing, reward or schema added. Actual combined-runtime LocalSession creation/replay and original 2B4C620/C17781 native branch pass: Quick Start changes only offset4379; ordinary still enters tutorial. Risk MEDIUM, no demonstrated defect. Natural GUI remains unverified. Final scope: 17 runtime files plus Program.cs.
