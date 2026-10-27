"""Verify deployed client-source bookkeeping without merging its feature PR."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.materialize_formal_runtime import bound,load_manifest,plan
def verify_source(row):
    raw=bound(ROOT,row['source']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==row['sha256']
    if 'size'in row:assert len(raw)==row['size']
def main():
    binding=json.loads((ROOT/'references/actual-native-final-ability-20261027-v1/binding.json').read_bytes())
    assert binding['source_PR']==583 and not binding['source_PR_merged']and not binding['server_backend_bytes_changed']and not binding['new_runtime_installation']
    assert binding['launcher_version']==40 and len(binding['captured'])==3
    expected={'tools/client_compatibility_profiles.json','tools/native_cache_sync.js','tools/native_cache_sync.py'}
    assert {r['path']for r in binding['captured']}==expected
    actual=load_manifest(ROOT/'channels/actual-periodic-runtime-with-v40-20261027-v1.json',ROOT)
    prior=load_manifest(ROOT/'channels/periodic-deadline-fairness-accepted-20261027-v3.json',ROOT)
    for mode in('online','local'):
        # All server/backend input bytes, including deadline fairness and
        # the separately delivered bank/path changes, are identical.
        values=lambda p:{e['path']:(e['size'],e['sha256'])for e in p['channels'][mode]['files']}
        assert values(actual)==values(prior)
    support={r['path']:r for r in actual['channels']['local']['retained_client_support_sources']};assert len(support)==5
    for row in binding['captured']:
        assert all(support[row['path']][k]==row[k]for k in('source','sha256'));verify_source(row)
    current=load_manifest(ROOT/'channels/current-engine.json',ROOT)
    counts={}
    for mode in('online','local'):
        plan(ROOT,current,mode)
        rows=current['channels'][mode].get('retained_client_support_sources',[])
        assert len({r['path']for r in rows})==len(rows)
        for row in rows:verify_source(row)
        counts[mode]=len(rows)
    print(json.dumps(dict(ok=True,inherited_deployed_V40_sources=3,server_backend_inputs_unchanged=True,
                         current_retained_support_sources=counts,PR583_merge_not_inferred=True,runtime_installation=False)))
if __name__=='__main__':main()
