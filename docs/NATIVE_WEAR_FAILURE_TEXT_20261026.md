# Native wear failure text and diagnostics

The current `105` consumer decodes its vector, removes wait 105 and passes the
signed result to the shared `751120/79B330` error handler. Generic server
rejections currently use -1, whose native message is empty. A successful unequip
can therefore remain committed while a later rejected request opens a blank
dialog. The original report did not record that rejected request's payload, so
its exact reason is not inferred from the later inventory state.

Use existing native result 1 for generic wear rejection and 1999 for the exact
activity-armor ordinary-unidentified condition. Preserve artifact result 2005.
Log the native source/destination, flag, envelope and exact rejection reason.
All actor, phase, ownership, bag/slot, expiry, durability and original wear
requirements remain in force. No stale request is accepted or relocated, and a
successful prior move is not reversed.

Original offline `105` prefix and result lookup confirm the nonblank messages.
Actual temporary TLS checks cover successful unequip followed by a stale
request, unchanged committed inventory/receipts, native 1/1999 decoding and
typed diagnostics. The activity ordinary-initial implementation is maintained
in its separate change; before that producer is installed, the new exact 1999
condition is simply unused. Formal/public and natural GUI checks are separate.
