# Tutorial dynamic actor declarations

The original tutorial scripts request actors 2065/2066 in Elsword map 41150 and
2186 in Rose map 41250. Their stage-zero dynamic declarations were incomplete.
This change supplies those declarations and the original two Elsword definitions
through the existing authoritative 2CE/2CF/2D0 flow. It changes two server data files.
Client scripts, UI, effects, AI, timing and reward processing remain native.

Local and online protection completed with separate SQLite API backups, original
rows/schema/configuration preserved, installed program checks and observations
of 123.62 and 127.69 seconds. Both channels contain the exact reviewed data.
The JSON uses LF and its companion manifest retains CRLF; their raw-byte hash
relationship is intentional. No player database rollback or installation DDL ran.

One owned public account with two standard API-created roles passed tutorial
admission, cached retry, stage and own-sentinel-envelope rejection, original
61/14A room/envelope checks, complete warm/cold 2A equality and 48D/48F fences.
Public persistence checks cover six named tables and character/items/balance/
slots/creation-receipt projections. They do not establish all-table invariance,
cross-account permissions, complete 61/14A trailer equality or multiplayer play.
No clear, reward or economic wire operation ran; the test account was disabled.

Independent post-delivery review passed. An inherited completion-summary label
says one delta; actual manifests, acceptance records and installed hashes confirm
two replacements. The historical label is retained with this correction.
Natural dynamic spawning, GUI and tutorial completion remain unverified.
Source/privacy/codec CI passed; source CI is separate from runtime acceptance.
Closes #264.
