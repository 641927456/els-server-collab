# Reject superseded dismount receipts

Owner: maintainer-coordinated independent server correction.
Base: current reviewed main; source/rules remain pinned to the existing native mount DTO and runtime asset lock.

Ride a mount, dismount successfully, then ride again (or switch mounts). Replaying the first dismount operation previously returned a successful native `430` while persistent state still said the current mount was ridden. This could send a stale dismount notification after a later operation had superseded it.

`storage/mount_state.py::handle` now rejects that old `42F` receipt unless the owner is currently on foot and the referenced mount is unmounted. The existing domain adapter emits its normal failure reply. Receipt, owner, current state and provisional clock settlement remain in the original SQLite writer transaction; rejection rolls it all back. A current on-foot retry still succeeds with one receipt. Existing stamina rules, clocks, item activation, UI, effects and native protocol remain unchanged. There is no schema migration or client change.

After installing the locked runtime assets as documented in README.md:

```powershell
python -B -m unittest discover -s tests -p test_mount_retry.py -v
python -B tools/ci_checks.py
git -c core.whitespace=cr-at-eol diff --check
```

Five focused cases cover same-mount and switched-mount stale retries, current successful retry, the domain failure reply, foreign ownership and conflicting operation identity. All databases are fresh temporary fixtures using the existing activation path; no player data or capture is included. Against the parent, three cases fail; the candidate passes all five. These are controlled persistence/domain tests, not naturally operated mount UI or full companion/combat acceptance. Deployment is a separate maintainer operation.
