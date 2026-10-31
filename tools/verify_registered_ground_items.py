"""Check the immutable source candidate without activating runtime profiles."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]

def verify():
    c=json.loads((ROOT/'references/registered-ground-items-20261101-v1/source-contract.json').read_bytes())
    assert c['candidate']and c['activation']is False and c['actual_dual_delivery_verified']is False
    assert not c['source_and_pool_probability_changes']and not c['player_databases_included']and not c['test_timer_shim_included']
    seen=set()
    for row in c['files']:
        key=(row['channel'],row['path']);assert key not in seen;seen.add(key)
        p=ROOT/row['source'];raw=p.read_bytes();assert len(raw)==row['size']and hashlib.sha256(raw).hexdigest()==row['sha256']
        assert p.resolve().is_relative_to((ROOT/'references/registered-ground-items-20261101-v1').resolve())
        if p.suffix=='.py':compile(raw,str(p),'exec')
    assert len(c['files'])==10
    launcher=ROOT/'references/registered-ground-items-20261101-v1/launcher/source-contract.json'
    if launcher.exists():
        release=json.loads(launcher.read_bytes());assert release['version']==59 and len(release['files'])==9
        for row in release['files']:
            p=ROOT/row['source'];raw=p.read_bytes();assert len(raw)==row['size']and hashlib.sha256(raw).hexdigest()==row['sha256']
            if p.suffix=='.py':compile(raw,str(p),'exec')
    print(json.dumps(dict(ok=True,source_files=len(seen),candidate_only=True)))

if __name__=='__main__':verify()
