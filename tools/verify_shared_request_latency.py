"""Verify the unselected latency candidate and its exact qualified mode deltas."""
import hashlib
import json
import argparse,subprocess,tempfile
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.materialize_formal_runtime import bound,load_manifest,plan,materialize

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--with-runtime',action='store_true')
    parser.add_argument('--assets-root',type=Path,default=ROOT)
    args=parser.parse_args()
    name='shared-request-latency-20261031-v1'
    candidate=load_manifest(ROOT/'channels/shared-request-latency-candidate-20261031-v1.json',ROOT)
    delta=json.loads((ROOT/'references'/name/'delta.json').read_bytes())
    parent=bound(ROOT,delta['parent'])
    assert hashlib.sha256(parent.read_bytes()).hexdigest()==delta['parent_sha256']
    old=json.loads(parent.read_bytes())
    selected=json.loads((ROOT/'channels/current-engine.json').read_bytes())
    assert delta['parent']==candidate['parent']
    assert selected['profile']!='channels/shared-request-latency-candidate-20261031-v1.json'
    assert candidate['candidate'] is True and candidate['actual_dual_delivery_verified'] is False
    assert candidate['new_schema'] is False and candidate['client_delta']==0
    counts={}
    expected={'els_server/'+p for p in (
        'application.py','domain/session_auxiliary.py','domain/pet_support_flow.py',
        'storage/inventory_state.py','storage/resonance_state.py','storage/character_custom.py',
        'storage/boosting_2026_force_inventory.py','storage/boosting_2026_nested_capacity.py',
        'storage/artifact_progression.py','storage/titles.py','storage/expansion_items.py',
        'storage/skill_unlocks.py','storage/boosting_2026_limited_pet.py','storage/town_dialogue.py')}
    for mode in ('online','local'):
        before={r['path']:r for r in old['channels'][mode]['files']}
        after={r['path']:r for r in candidate['channels'][mode]['files']}
        changed={p for p in before.keys()|after.keys()if before.get(p)!=after.get(p)}
        assert changed==set(delta['channels'][mode])==expected
        for path,change in delta['channels'][mode].items():
            assert change['before']==before.get(path) and change['after']==after[path]
            source=bound(ROOT,after[path]['source'])
            compile(source.read_text(encoding='utf8'),str(source),'exec')
        plan(ROOT,candidate,mode)
        counts[mode]=len(after)
    print(json.dumps(dict(ok=True,candidate_only=True,changed_files_per_mode=len(expected),files=counts)))
    if args.with_runtime:
        cache=ROOT/'.runtime-cache';cache.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='shared-latency-',dir=cache)as folder:
            for mode in ('online','local'):
                view=Path(folder)/mode
                materialize(ROOT,candidate,mode,view,assets_root=args.assets_root,link_assets=True)
                runner="""import os,sys,tempfile,unittest
from pathlib import Path
runtime=Path(sys.argv[1]);source=Path(sys.argv[2])
sys.path.insert(0,str(runtime))
import els_server
assert Path(els_server.__file__).resolve()==runtime/'els_server/__init__.py'
sys.path.insert(0,str(source/'tests'));tempfile.tempdir=str(runtime.parent)
os.environ['ELS_RUNTIME_ROOT']=str(runtime)
suite=unittest.TestSuite()
for name in ('test_declining_consumers','test_auxiliary_worker_activity'):
 suite.addTests(unittest.defaultTestLoader.loadTestsFromName(name))
result=unittest.TextTestRunner().run(suite)
assert result.testsRun==31 and not result.skipped
raise SystemExit(not result.wasSuccessful())
"""
                subprocess.run([sys.executable,'-B','-c',runner,str(view),str(ROOT)],cwd=view,check=True)

if __name__=='__main__':
    main()
