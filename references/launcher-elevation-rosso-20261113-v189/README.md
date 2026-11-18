# V189 accepted source archive

Six runtime leaves and two launcher source changes; all result/parent hashes are in changeset.json. No logs, credentials, databases, binaries or private configuration are archived.

Program.cs is a standard unified diff against the existing V188 archive, avoiding duplication of its old random self-test placeholder. Reconstruct in a private empty directory without checkout:

```powershell
python -c "import pathlib,subprocess; pathlib.Path('Program.cs').write_bytes(subprocess.check_output(['git','show','f9c7bf58123c47d4ab490d73863d544304560a58:references/consolidated-repairs-20261113-v188/launcher-source/Program.cs']))"
git apply --whitespace=nowarn Program.cs.patch
Get-FileHash -Algorithm SHA256 Program.cs
```

The result must match the Program.cs SHA in changeset.json. submit_sources.py checks exact reconstruction in its own temporary directory before writing Git objects.

This commit records an accepted source archive only. Main merge, push and approval remain separate. Natural UI, UAC prompt and Rosso combat/reward acceptance are not claimed.
