"""Check exact qualified V39 source variants separately from future attribute work."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.materialize_formal_runtime import load_manifest,plan,bound

def main():
    folder=ROOT/'references/native-power-cache-sync-20261027-v1'
    candidate=json.loads((folder/'candidate.json').read_bytes())
    assert candidate['installed']and candidate['native_qualification_complete']
    assert not candidate['original_executable_changed']and not candidate['original_resource_archives_changed']and not candidate['new_damage_formula']
    assert len(candidate['files'])==8 and len({r['path']for r in candidate['files']})==8
    for row in candidate['files']:
        assert hashlib.sha256(bound(folder,row['path']).read_bytes()).hexdigest()==row['sha256'],row['path']
    profile=load_manifest(ROOT/'channels/current-engine.json',ROOT)
    plan(ROOT,profile,'local')
    retained=profile['channels']['local']['retained_client_support_sources']
    assert len(retained)==5
    final_ability=profile['channels']['local'].get('native_final_ability_sync',False)
    if final_ability:
        final_folder=ROOT/'references/native-final-ability-sync-20261027-v1'
        final_candidate=json.loads((final_folder/'candidate.json').read_bytes())
        assert final_candidate['installed']and final_candidate['native_qualification_complete']
        mapping=final_candidate['runtime_variants']['local']
        assert {row['path']for row in retained}==set(mapping)
        for row in retained:
            source=bound(final_folder,mapping[row['path']])
            assert bound(ROOT,row['source'])==source
            assert hashlib.sha256(source.read_bytes()).hexdigest()==row['sha256'],row['path']
    else:
        for row in retained:
            assert hashlib.sha256(bound(folder,row['path']).read_bytes()).hexdigest()==row['sha256'],row['path']
    hosts=json.loads((folder/'approved-hosts.json').read_bytes())
    assert hosts['unknown_hosts_refused']and hosts['trace_file_changes']==0
    summary=json.loads((folder/'delivery-summary.json').read_bytes())
    assert summary['launcher_version']==39 and summary['native_families']==15 and summary['controlled_native_career_projections']==195
    assert summary['cold_native_Actors']==15 and summary['cache_repair_complete']and not summary['whole_user_goal_complete']
    print(json.dumps(dict(ok=True,qualified_archive_files=8,retained_LOCAL_support_files=5,
                         native_families=15,controlled_careers=195,
                         full_attribute_draft_not_selected=not final_ability,runtime_actions=0)))

if __name__=='__main__':main()
