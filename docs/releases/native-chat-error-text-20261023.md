# Native generic chat error

The existing chat rejection sentinel -1 falls outside the client's original
message table, producing an empty error string. `chat_ack` now maps only -1 to
the native generic failure code 1. Its default result remains 0; success 0,
specific code 3 and all other protocol functions retain their original behavior.
Client text, UI and timing are reused. Authentication, stage and channel checks
are unchanged.

The single module was installed locally and online with separate SQLite API
backups, original rows/schema/configuration preserved, installed program checks
and observations of 122.70 and 121.70 seconds. No installation DDL or player
database rollback occurred; previous independent fixes remain present.

One owned public account and standard API-created role passed an invalid 85
request in the authenticated map-loading phase. The complete 86 response contains
the four-byte failure result 1, identically before and after cold selection.
A legal 48D/48F metadata fence confirms no 87 echo. Selected character, inventory,
balance, progression, skill-slot and creation-receipt projections remain equal.
The account was disabled; no creation, economic or key-save wire request ran.

Independent post-delivery review passed. Source/privacy/codec CI passed separately
from runtime acceptance. Compatibility of success 0 and specific 3 is a builder
check, not a new positive public-chat test. Valid chat, natural error popups, GUI,
other channels, cross-scene behavior and multiplayer remain outside this test.
No complete-system or all-table public verification is claimed.
Closes #265.
