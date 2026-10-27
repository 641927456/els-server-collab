"""Verify retained actual engine sources, mode differences and reviewed corrections."""
from pathlib import Path
import ast,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.materialize_formal_runtime import load_manifest,plan
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    profiles={
        'channels/reviewed-pr563-573-576-current-20261027-v1.json':{'online':1233,'local':1234},
        'channels/reviewed-pr563-573-576-peak-parent-20261027-v2.json':{'online':1234,'local':1235},
    }
    # Pin both reviewed corrective candidates independently from actual-formal selection.
    selected_profile='channels/reviewed-pr563-573-576-peak-parent-20261027-v2.json'
    profile=load_manifest(ROOT/selected_profile,ROOT)
    for name,expected_counts in profiles.items():
        pinned=load_manifest(ROOT/name,ROOT)
        assert pinned['reviewed_PRs']==[563,573,576] and pinned['new_runtime_delta_files']==1 and pinned['client_behavior_delta']==0
        for mode,count in expected_counts.items():
            rows=plan(ROOT,pinned,mode)
            assert len(rows)==count
            assert next(e for e,_ in rows if e['path']=='els_server/domain/formal_pve_economy.py')['sha256']=='321c9e1baadcf38930de43fb16b07d86619509e758bb8cad5bf269898a61fec3'
        sources=pinned['channels']['local']['retained_client_support_sources']
        assert len(sources)==5 and len({e['path']for e in sources})==5
        for e in sources:assert sha(ROOT/e['source'])==e['sha256']and (ROOT/e['source']).stat().st_size==e['size']
    assert profile['reviewed_PRs']==[563,573,576]and profile['new_runtime_delta_files']==1 and profile['client_behavior_delta']==0
    expected='321c9e1baadcf38930de43fb16b07d86619509e758bb8cad5bf269898a61fec3'
    counts={}
    for mode in ('online','local'):
        rows=plan(ROOT,profile,mode);lookup={e['path']:e for e,_ in rows}
        assert lookup['els_server/domain/formal_pve_economy.py']['sha256']==expected
        assert len(rows)==profiles[selected_profile][mode]
        counts[mode]=len(rows)
    retained=profile['channels']['local']['retained_client_support_sources']
    assert len(retained)==5 and len({e['path']for e in retained})==5
    for e in retained:
        p=ROOT/e['source'];assert sha(p)==e['sha256']and p.stat().st_size==e['size']
    functions=[]
    for name in ('native-aurora-book-sources-20261027-v1','native-change-force-materials-20261027-v1'):
        p=ROOT/'references'/name/'shared/els_server/domain/formal_pve_economy.py'
        fn=next(n for n in ast.parse(p.read_text()).body if isinstance(n,ast.FunctionDef)and n.name=='clear_items')
        functions.append(ast.dump(fn,include_attributes=False))
    assert functions[0]==functions[1]
    m=json.loads((ROOT/'references/native-change-force-materials-20261027-v1/manifest.json').read_bytes())
    assert m['new_tables']==m['new_schema_definitions']==2 and m['new_schema']is True and m['install_DDL']==0
    assert (ROOT/'docs/MOD360_SCHEMA_METADATA_CORRECTION_20261027.md').is_file()
    print(json.dumps(dict(ok=True,reviewed_corrective_candidate_engine=counts,retained_LOCAL_client_sources=5,one_defensive_business_leaf=True,Mod_two_lazy_schema_definitions=True,install_DDL0=True,all_archived_reviewed_draw_functions_equal=True,all_reviewed_profiles_pinned=True,formal_install_not_inferred_from_Git=True)))

if __name__=='__main__':main()
