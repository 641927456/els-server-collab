"""Prepare an isolated, hash-bound runtime; leave installed sources untouched."""
import hashlib
import json
import shutil
from pathlib import Path

W = Path(__file__).resolve().parent
R = W.parents[1]
C = W/'candidate'
assert not C.exists()
pointers = {ch:json.loads((R/f'releases/{ch}/current.json').read_bytes()) for ch in ('online','local')}
parent = R/pointers['online']['path']
raw = (parent/'rollup-manifest.json').read_bytes()
assert hashlib.sha256(raw).hexdigest() == pointers['online']['manifest_sha256']
manifest = json.loads(raw)
C.mkdir()
for row in manifest['files']:
    src = parent/row['path']
    raw = src.read_bytes()
    assert len(raw) == row['size'] and hashlib.sha256(raw).hexdigest() == row['sha256'], row['path']
    dst = C/row['path']
    dst.parent.mkdir(parents=True,exist_ok=True)
    dst.write_bytes(raw)
binding = dict(parent=pointers['online'],parent_root=str(parent),local_parent=pointers['local'],candidate=str(C),
    human_instruction='除开普通时装散件，然后把其他的可以上架的进行上架',
    authorization_date='2026-11-04 Asia/Hong_Kong',
    scope='Qualify and list missing complete costume/fan packages and ordinary cash accessories. Preserve every existing standalone fashion offer and all unrelated channel differences. Release only via designated publisher.',
    price_ED=50,original_EXE_KOM_modified=False,publication_authority=False,Git_merge_authority=False)
(W/'update-binding.json').write_text(json.dumps(binding,ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps(dict(ok=True,files=len(manifest['files']),MiB=sum(x['size']for x in manifest['files'])//1048576)))
