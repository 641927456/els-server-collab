"""Verify the unselected latency candidate and the exact two-leaf mode deltas."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.materialize_formal_runtime import bound,load_manifest,plan

def main():
    name='shared-request-latency-20261031-v1'
    candidate=load_manifest(ROOT/'channels/shared-request-latency-candidate-20261031-v1.json',ROOT)
    delta=json.loads((ROOT/'references'/name/'delta.json').read_bytes())
    parent=bound(ROOT,delta['parent'])
    assert hashlib.sha256(parent.read_bytes()).hexdigest()==delta['parent_sha256']
    old=json.loads(parent.read_bytes())
    selected=json.loads((ROOT/'channels/current-engine.json').read_bytes())
    assert selected['profile']==delta['parent']==candidate['parent']
    assert candidate['candidate'] is True and candidate['actual_dual_delivery_verified'] is False
    assert candidate['new_schema'] is False and candidate['client_delta']==0
    counts={}
    for mode in ('online','local'):
        before={r['path']:r for r in old['channels'][mode]['files']}
        after={r['path']:r for r in candidate['channels'][mode]['files']}
        changed={p for p in before.keys()|after.keys()if before.get(p)!=after.get(p)}
        assert changed==set(delta['channels'][mode])=={'els_server/application.py','els_server/domain/session_auxiliary.py'}
        for path,change in delta['channels'][mode].items():
            assert change['before']==before.get(path) and change['after']==after[path]
            source=bound(ROOT,after[path]['source'])
            compile(source.read_text(encoding='utf8'),str(source),'exec')
        plan(ROOT,candidate,mode)
        counts[mode]=len(after)
    print(json.dumps(dict(ok=True,candidate_only=True,changed_files_per_mode=2,files=counts)))

if __name__=='__main__':
    main()
