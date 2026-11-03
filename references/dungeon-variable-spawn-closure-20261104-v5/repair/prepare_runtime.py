import hashlib,json,os,shutil
from pathlib import Path
W=Path(__file__).resolve().parent;M=json.loads((W/'candidate-manifest.json').read_bytes());R=Path(M['parent_runtime']);D=W/'runtime';C=W/'candidate'
H=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert not D.exists(),'Fresh owned runtime required'
assert H(R/'rollup-manifest.json')==M['parent_manifest_sha256']
for row in json.loads((R/'rollup-manifest.json').read_bytes())['files']:
 source=R/row['path'];target=D/row['path'];assert H(source)==row['sha256']
 target.parent.mkdir(parents=True,exist_ok=True);os.link(source,target)
for row in M['files']:
 source=C/row['path'];target=D/row['path'];assert H(source)==row['sha256']
 if target.exists():target.unlink()
 target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
(W/'runtime-preparation.json').write_text(json.dumps(dict(runtime=str(D),parent=str(R),changed_files=M['files'],owned=True),indent=2),encoding='utf8')
print('Prepared isolated current-parent runtime; original files only read.')
