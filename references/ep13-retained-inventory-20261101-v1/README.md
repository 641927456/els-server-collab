# EP13 retained inventory compatibility

Four current saved item templates were missing from the installed shared retained-item reader: 716611, 718783, 720017 and 720835. An inventory read could fail before quest100550 reached its normal reward transaction. This archive preserves the exact two installed files and their increment; the original46 definitions remain unchanged.

The normal quest objective, character eligibility, reward710098, successor100560, transaction and duplicate-request handling are unchanged. New generic acquisition/consumption remains closed. There is no schema or client change.

`source-contract.json` pins both source files and the inherited rows. `native-result.json` records six unchanged native item reader/classifier vectors. `installed-verification.json` contains only the redacted dual installation/public TLS summary. The maintainer retains private original evidence outside Git.

The repository mainline has not yet integrated the installed shared retained-item pipeline. These are deployment-source references, following the existing source-archive convention, and must be integrated with that pipeline rather than overwriting older active modules. `source_merged=false` is intentional. Run `python -B tools/verify_ep13_retained_inventory_sources.py` to validate this source archive without private assets.

The missing readers are a verified blocker. The reported generic2005 popup has not been attributed to one captured F4/F5 pair; this change does not claim to resolve every possible reason for that text. Natural GUI clicking was not tested.
