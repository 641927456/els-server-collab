# Current decomposition receipt projection

Status: candidate validated privately; protected online/local acceptance pending.
Issue: #49. Owner: maintainer-coordinated independent server correction.

An internal ordinary-decomposition call reusing the same authenticated operation previously refreshed only historical inventory positions. A retained affected UID that later moved was omitted. Reuse the existing current-state receipt projection for `1C0`: old positions contain their present replacement or empty row, and retained affected UIDs add their current owned positions. Consumed or other-role UIDs are not recreated or selected by template.

Only `storage/decomposition.py` and the reviewed-kind tuple in `storage/equipment_receipt_state.py` change. Fresh decomposition eligibility, removal/grant transaction, yield, request-hash binding and commit code remain unchanged. There is no schema, source, probability, client or launcher change.

Private full-runtime SQLite/domain checks reproduced three parent failures and passed six focused cases in each channel, including legitimate shared-bank transfer, conflicting request identity and encoder rollback. These sanitized results do not include the private fixtures or logs. Portable tests require only Python and a temporary SQLite file, with projection-only rows and no invented item/reward definitions:

```powershell
python -B -m unittest discover -s tests -p test_decomposition_receipt_projection.py -v
python -B tools/ci_checks.py
git -c core.whitespace=cr-at-eol diff --check
```

The portable cases verify UID movement, current counts, replacements of old slots, another role, consumed/unrelated UIDs, owner/kind conflicts and malformed history. The production caller must still authenticate the request digest through `_previous`; these projection tests do not replace the full transaction checks.

Public secure frame sequences remain strictly increasing. Repeating an old outer frame is rejected before business logic; a fresh sequence with an already-consumed source is a new operation and fails. Private same-operation storage/domain re-calls are not natural reconnect or positive public TLS replay acceptance. Natural decomposition UI and complete crafting/synthesis gameplay remain unclaimed.
