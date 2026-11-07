"""Archive integrity and actual native-input binding; does not claim runtime tests."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parent
manifest=json.loads((ROOT/'manifest.json').read_bytes())
assert manifest['status']=='REVIEWED_CANDIDATE_NOT_INSTALLED'
assert not manifest['production_installed']and not manifest['main_merged']
for name,row in manifest['files'].items():
    path=ROOT/name;assert path.resolve().is_relative_to(ROOT.resolve())
    raw=path.read_bytes();assert len(raw)==row['size']and hashlib.sha256(raw).hexdigest()==row['sha256'],name
    if path.suffix=='.py':compile(raw,str(path),'exec')
actual={p.relative_to(ROOT).as_posix()for p in ROOT.rglob('*')if p.is_file()and '__pycache__'not in p.parts}
assert actual==set(manifest['files'])|{'manifest.json'}
native=json.loads((ROOT/'evidence/native-full-status-qualification.json').read_bytes())
assert native['ok']and native['native_result']['fresh_zero_UI']and native['native_result']['restores']==2
assert native['input_desktop_unchanged']and native['original_EXE_unchanged']and not native['production_database_access']
for name,digest in native['source_hashes'].items():
    assert hashlib.sha256((ROOT/'source-v1'/name.replace(chr(92),'/')).read_bytes()).hexdigest()==digest,name
print(json.dumps(dict(ok=True,files=len(manifest['files']),actual_native_input_files=len(native['source_hashes']),
    production_installed=False,natural_GUI=False,scope='archive/source binding only; recorded runtime results are separate')))
