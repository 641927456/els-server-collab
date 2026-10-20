# Friends V32 startup support modules

Official V32 publication and public update acceptance completed. Release identity is in `release.json`. Git does not deploy the launcher or server.

The nine C# files are preserved from V31 with exactly two literal substitutions: `Program.PayloadHash` and `AutoUpdate.Version`. The signed component manifest changes accordingly. Layout, credentials/DPAPI, updater, diagnostics and transport logic are unchanged. The previous V31 directory is untouched.

`runtime-support/` contains only the three exact launcher variants of the qualified Python cold-load modules. They retain the inventory/slot/manufacturing results and generated-JS bytes; no game EXE/KOM, resources, JS, probe or Hook changes are included. This launcher variant must not be replaced with an entire online/local inventory file.

Build with the existing V29 asset archive and reused lock; no assets, runtime ZIP, EXE, signing key, account or log is stored here:

```powershell
python launchers/friends-v32/build.py --assets .asset-cache/ELS-V29-Build-Assets.zip --output .asset-cache/ELS-Friends-V32-built.exe
python -B -m unittest discover -s tests -p 'test_launcher_v32_source.py' -v
```

The small shell embeds the signed manifest, not the runtime ZIP. Rebuilding can change the overall PE identity; official publication bytes remain identified in `release.json`. Source tests require no compiler, runtime assets, network or game. Natural end-to-end GUI speed is not claimed by controlled import/consumer evidence.
