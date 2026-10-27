"""Verify complete-attribute source bindings; native observations remain separate."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.materialize_formal_runtime import bound,load_manifest,plan

def main():
    folder=ROOT/'references/native-final-ability-sync-20261027-v1'
    candidate=json.loads((folder/'candidate.json').read_bytes())
    index={row['path']:row for row in candidate['files']}
    assert len(index)==len(candidate['files'])==8
    for row in index.values():
        assert hashlib.sha256(bound(folder,row['path']).read_bytes()).hexdigest()==row['sha256']
    for mapping in candidate['runtime_variants'].values():
        registry=json.loads(bound(folder,mapping['tools/client_compatibility_profiles.json']).read_bytes())['profiles'][0]['artifacts']
        assert set(mapping)=={'tools/native_cache_sync.py','tools/native_cache_sync.js','tools/probe_updated_client.py','tools/client_compatibility.py','tools/client_compatibility_profiles.json'}
        for path,source in mapping.items():
            if path!='tools/client_compatibility_profiles.json':
                assert registry[path]==hashlib.sha256(bound(folder,source).read_bytes()).hexdigest()
    assert not candidate['original_executable_changed']and not candidate['original_resource_archives_changed']and not candidate['new_damage_or_healing_formula']
    if candidate['native_qualification_complete']:
        qualification=folder/'qualification-summary.json'
        assert hashlib.sha256(qualification.read_bytes()).hexdigest()==candidate['qualification_summary_sha256']
        qualified=json.loads(qualification.read_bytes())
        assert qualified['native_families']==15 and qualified['controlled_native_careers']==195 and qualified['cold_native_Actors']==15
        assert len({c for row in qualified['cases']for c in row['controlled_classes']})==195
        assert qualified['original_native_buff_layers_preserved']and qualified['independent_original_prefix_observed_before_C4_hook']
    current=load_manifest(ROOT/'channels/current-engine.json',ROOT)
    selected=current['channels']['local'].get('native_final_ability_sync',False)
    if selected:
        assert candidate['native_qualification_complete']and candidate['installed']
        delivery=folder/'delivery-summary.json'
        assert hashlib.sha256(delivery.read_bytes()).hexdigest()==candidate['delivery_summary_sha256']
        summary=json.loads(delivery.read_bytes())
        assert summary['launcher_version']==40 and summary['native_families']==15 and summary['controlled_native_careers']==195 and summary['cold_native_Actors']==15
        assert summary['native_final_ability_sync']and summary['original_native_buff_layers_preserved']
        mapping=candidate['runtime_variants']['local_formal'];retained=current['channels']['local']['retained_client_support_sources']
        assert len(retained)==5 and {r['path']for r in retained}==set(mapping)
        for row in retained:
            source=bound(folder,mapping[row['path']]);assert bound(ROOT,row['source'])==source
            assert source.stat().st_size==row['size']and hashlib.sha256(source.read_bytes()).hexdigest()==row['sha256']
        for channel in('online','local'):plan(ROOT,current,channel)
    print(json.dumps(dict(ok=True,archive_files=8,approved_runtime_variants=2,selected_complete_attribute_release=selected,native_qualification_claimed=candidate['native_qualification_complete'],runtime_actions=0)))

if __name__=='__main__':main()
