# Paid town-warp continuation

After a successful `58C/58D` teleport, the current native client sends
`225(destination, 1)` before its normal `227` arrival. The old ordinary-town
handler rejects flag 1 after the fee and destination have already committed,
then closes the connection. The native error lookup also maps the old generic
result -1 to an empty string, producing the earlier blank dialog.

Accept that flag only for the current actor, session, later request sequence,
exact pending successful warp, committed receipt digest/response and saved paid
destination. Receipt verification is read-only and never charges again.
Village 1012 continues to use its stricter existing committed-entry reader.
Unbound flag 1, other destinations, obsolete leases and invalid envelopes remain
closed. Preserve existing walking, cold-entry and the source branch's original
Noah return handling; no unrelated Lithia adaptation is added to the main source.

Use the existing native 1355 message for insufficient ED and 1 for other generic
failures, while retaining the original 653 requirement details. Fees, passes,
unlock requirements and acquisition sources do not change.

Original offline x64 sender and result-lookup replay verified the flag and
nonblank strings. The two actual formal-parent private TLS flows cover all 16
ordinary/rest destinations available to the tested type, legacy flag 0, native
flag 1, single debit, invalid destination/flag/width/sequence/session/lease
rejection and unchanged state on failure. The public QA harness is qualified in
an owned temporary store and includes cold destination/inventory verification,
exact account cleanup and registration-capacity checks. Formal deployment and
public acceptance remain separate frozen receipts. Natural GUI and other
character-specific birth-town acceptance are not claimed by these checks.

This change adds no client files, database schema or player-save migration.
Git synchronization itself does not restart a service.
