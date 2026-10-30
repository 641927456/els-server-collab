"""Exact complete PR635 source archive; no runtime installation claim."""
from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parents[1];P=R/'references/local-repairs-20261030-v1';d=json.loads((P/'source-contract.json').read_bytes())
assert d['candidate_only'] and not d['installed'] and not d['root_runtime_changed']
assert d['original_head']=='f2ef13bd78dfac9b2c36543dcf5410b3cc82caec' and len(d['files'])==119
assert len({r['path']for r in d['files']})==119
for row in d['files']:
 source=R/row['source'];assert source.resolve().is_relative_to((P/'source').resolve())
 raw=source.read_bytes();assert len(raw)==row['size'] and hashlib.sha256(raw).hexdigest()==row['sha256'],row['path']
 if source.suffix=='.py':compile(raw,str(source),'exec')
print('PR635: all119 original source files match, Python syntax valid; candidate only')
