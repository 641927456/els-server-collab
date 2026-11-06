Task reward repairs, Issue #860

This is a reference-only archive of 26 exact server source/data files. It repairs quest furniture, four PvP reward boxes, pet nutrition/digestive use, Camilla stone exchange and the specialization/enchant use chain. Repository-root runtime and channel selectors are unchanged.

Specialization uses the user-requested local rule: choose/change starts at level 1; each fragment enchant advances one level; level 10 is the current-client maximum. Current-client material/AP costs are retained. This is not a retail probability claim. Accessory cubes use the separately approved fixed permanent sets.

Existing inventory/action receipts and authoritative official PvP AP profiles are reused. Furniture migration preserves item UIDs and old quest receipts. Pet digestion adds an optional JSON deadline with zero default; no installation DDL or alternate AP ledger is introduced.

validation-summary.json contains sanitized results from actual private SQL, actual Application/FriendsSession dispatch and pinned native-code writer/reader replay. Verification scripts retain the original private-workspace paths for reviewing and reproducing assertions in an authorized resource workspace. They require the matching materialized runtime and private locked assets; no database, executable, KOM, process image, credential, capture or operational log is included here. Test AP balances are explicit private fixtures, not fabricated live matches.

Natural GUI, real battle stat application and actual production installation remain separate. The publication owner must bind the actual running parent, back up code and both databases, drain normally, install and verify the running result under the existing release flow. This archive does not authorize merge bypass or deployment by other chats.

Source integrity check: python -B refs/task-reward-repairs-20261105-v1/verify_archive.py
