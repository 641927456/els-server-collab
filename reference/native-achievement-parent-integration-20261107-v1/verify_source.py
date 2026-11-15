"""Resolve the exact archive leaves used by this independently qualified composition."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
manifest=json.loads((HERE/'source-manifest.json').read_bytes())
assert not manifest['production_installed']and not manifest['main_merged']
for row in manifest['source_files']:
    path=ROOT/row['source'];assert path.resolve().is_relative_to(ROOT.resolve())
    raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==row['sha256'],row['target']
    if path.suffix=='.py':compile(raw,str(path),'exec')
qualification=json.loads((HERE/manifest['qualification']).read_bytes());assert qualification['ok']and len(qualification['checks'])==12
for row in qualification['checks']:
    path=HERE/'evidence'/Path(row['path']).name
    assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256']and json.loads(path.read_bytes())['ok']
print(json.dumps(dict(ok=True,source_files=len(manifest['source_files']),private_checks=12,production_installed=False)))
