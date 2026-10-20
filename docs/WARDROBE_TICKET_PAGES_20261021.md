# Static wardrobe ticket page compilation

Native 0x563 ticket pages previously opened the immutable definition database for each uncached template. A bounded page-byte cache now compiles each cold page using one connection and batches of at most 900 IDs. The key includes the validated ClientData instance, client/catalog identities and complete ordered page inputs. Page and force flags remain request-local; player data, acquisition rules and client behavior are unchanged.

Parent source SHA256: `05a617508f2d1d8e00bd65f137af0379570d503921150397f773a9e1f6a546a1`. Frozen candidate: `98a2f0aa66005cdec5c1c24e102a9929736a746e02a3f7987860a8f3d45a95ec`. Other existing functions retain identical ASTs. No schema, runtime-resource or public game-data module changes are required. The existing immutable pack validation and new-instance-on-pack-change contract remains in force.

The private comparison verified all 45 pages with force 0/1 byte-for-byte, invalid inputs, changed validated pack/catalog inputs and concurrent compilation. Connections across the 90 responses fell from 76,656 to 45; a cached repeat used zero. Reuse those completed inputs rather than repeating the full private group.

Portable checks: `python -B tests/test_wardrobe_ticket_pages.py` uses private synthetic SQLite definitions to cover batching, native field order/duplicates/force, invalid input, source changes, concurrent compilation, failed-build retry and the 64-entry bound. No runtime assets or player saves are needed.

At this commit, controlled online/local installation is pending with the maintainer. Git merge does not deploy either channel. Natural player/GUI loading and full startup latency acceptance remain unverified; backend page equivalence does not imply those broader results.
