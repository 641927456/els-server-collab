from pathlib import Path
import hashlib,json
ROOT=Path('G:/els');B=ROOT/'analysis/pr771-firstbatch-20261103-v1';G=B/'git';R=B/'runtime'
BASE=ROOT/'releases/online/native-entry-boost-reward-sync-20261102-v1'
def sources():
    prior={r['path']:r for r in json.loads((G/'references/pr771-racing-reset-20261103-v1/combined-files.json').read_bytes())['files']}
    old={r['path']:r for r in json.loads((G/'references/pr771-firstbatch-20261103-v1/parent-manifest.json').read_bytes())['files']}
    old.update(prior);out={}
    for p in (R/'els_server').rglob('*'):
        if p.suffix not in('.py','.json')or '__pycache__'in p.parts:continue
        rel=p.relative_to(R).as_posix();digest=hashlib.sha256(p.read_bytes()).hexdigest()
        if rel not in old or digest!=old[rel]['sha256']:out[rel]=digest
    return dict(sorted(out.items()))
