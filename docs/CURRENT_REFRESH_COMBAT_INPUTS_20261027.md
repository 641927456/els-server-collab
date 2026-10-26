# Current combat inputs in full role refreshes

Quest rewards (F5) and career changes (D9) encode full role snapshots. Their
partial storage projection omitted the selected title and eligibility context,
skill traits and pages, force ownership and slots, and cleared-map context.
This could replace current native inputs with empty defaults after login.

The owned quest projection now reads those fields from its existing SQL
connection using the established readers. Career notifications refresh the
same fields from that connection after validating class, level and revision.
Unowned legacy rows keep their existing handling. There is no new attribute
formula, item source, schema, installation DDL or client behavior.

Validation used an isolated owned store and the real Application. Full native
DTO consumption and skill bytes matched the canonical cold projection from
the same SQL snapshot, both without forces and after an existing book's real
use/equip consumers populated a passive slot. Tests also covered cross-account
rejection, uncommitted title/trait changes, career D9 and transaction rollback.
The native reader uses executable SHA
`6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709`.

Natural GUI quest/career refresh, every skill's final damage, and multiplayer
battle are outside these checks. Deployment uses separate frozen manifests;
this PR alone does not install or restart a service.

Closes #553.
