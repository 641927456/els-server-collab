# V190 launcher-only append

Runtime/server remain V189 at d28790c2a798c1d30d02a7479778da27d0a29207. This commit adds only Program cumulative standard patch, MotionControls.cs, AutoUpdate.cs and sanitized provenance/verification.

Reconstruct Program.cs in a private empty directory: export raw Git bytes of d28790c2a798c1d30d02a7479778da27d0a29207:references/consolidated-repairs-20261113-v188/launcher-source/Program.cs using subprocess.check_output/Path.write_bytes, run git apply --whitespace=nowarn Program.cs.patch, then compare the SHA in changeset.json. No old random fixture placeholder is duplicated.

No logs, private configuration, credentials, databases or binaries are included. Natural UI/UAC acceptance is not claimed. No merge action.
