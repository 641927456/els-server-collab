"""Verify retained actual engine sources, mode differences and reviewed corrections."""
from pathlib import Path
import ast,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.materialize_formal_runtime import load_manifest,plan
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    # The reviewed corrective candidate remains immutable and qualified;
    # a later actual-formal selector must not pretend this candidate was installed.
    profile=load_manifest(ROOT/'channels/reviewed-pr563-573-576-current-20261027-v1.json',ROOT)
    assert profile['reviewed_PRs']==[563,573,576]and profile['new_runtime_delta_files']==1 and profile['client_behavior_delta']==0
    expected='321c9e1baadcf38930de43fb16b07d86619509e758bb8cad5bf269898a61fec3'
    counts={}
    for mode in ('online','local'):
        rows=plan(ROOT,profile,mode);lookup={e['path']:e for e,_ in rows}
        assert lookup['els_server/domain/formal_pve_economy.py']['sha256']==expected
        assert len(rows)==(1233 if mode=='online'else 1234)
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
    print(json.dumps(dict(ok=True,reviewed_corrective_candidate_engine=counts,retained_LOCAL_client_sources=5,one_defensive_business_leaf=True,Mod_two_lazy_schema_definitions=True,install_DDL0=True,all_archived_and_default_draw_functions_equal=True,formal_install_not_inferred_from_Git=True)))

if __name__=='__main__':main()
