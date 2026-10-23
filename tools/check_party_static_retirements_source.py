"""Static boundary of the finite34320 shared-controller receiver; opens no database."""
import argparse,ast,hashlib,json,subprocess
from pathlib import Path

EXPECTED={
 'els_server/domain/story_controller_retirements.py':('7b609e92fdf7bc601b2e1af2b08d56edcd7bdaf355ef3f7aa5ede38b3781e5b7','bb70015a0d325afb89c02edc3330884dd82701da399e855df3285026cd6a3375'),
 'els_server/domain/friends_story_retirements.py':(None,'c192e3a29070c2e0a1351bd6a1217bfad38419e9f15081a61aed38ef561db550'),
 'els_server/storage/seal_quests.py':('222f9d19c3538cad0f43e532cf8c886360bdb7cfa4f9f5e5bbf72e617a5b2d19','4ccede87913ceb93d2a12afb18f418892e10702e6c68a6a9ab6628eb0bc77640'),
 'els_server/domain/friends_dungeon.py':('bf1950572db72f95d389b86fa47c9b08684374baa501da40509e71318a03e99b','91106f8507002d0137c9db07214dcf04bb036327adf09ba4d9e50fbbb632e93c'),
 'els_server/domain/dungeon_flow.py':('db446ef37662e6e9089104bf2ef3e91a52889e371ebfc6a517357559e1c9395a','8f532490bdd2b9b7ff05390045697bd93203251ac50a322fb0f7516217d8a27f')}

def tree(raw):return ast.parse(raw)
def shape(node):return ast.dump(node,include_attributes=False)
def literal(t,name):
    return ast.literal_eval(next(n.value for n in t.body if isinstance(n,ast.Assign)
        and any(isinstance(v,ast.Name) and v.id==name for v in n.targets)))
def funcs(t):return {n.name:n for n in t.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[1]);ap.add_argument('--base',required=True)
    args=ap.parse_args();root=args.repo.resolve();base={};candidate={};rows=[]
    for rel,(parent_sha,candidate_sha) in EXPECTED.items():
        raw=(root/rel).read_bytes();assert hashlib.sha256(raw).hexdigest()==candidate_sha,rel
        candidate[rel]=tree(raw)
        old=subprocess.run(['git','show',args.base+':'+rel],cwd=root,capture_output=True)
        if parent_sha is None:assert old.returncode!=0,rel
        else:
            assert old.returncode==0 and hashlib.sha256(old.stdout).hexdigest()==parent_sha,rel
            base[rel]=tree(old.stdout)
        rows.append(dict(path=rel,parent_sha256=parent_sha,candidate_sha256=candidate_sha))
    rel='els_server/domain/story_controller_retirements.py';old=base[rel];new=candidate[rel]
    assert literal(new,'RULES')==literal(old,'RULES') and len(literal(new,'RULES'))==95
    for name,node in funcs(old).items():assert shape(node)==shape(funcs(new)[name]),name
    sources=literal(new,'_SHARED_34320_SOURCES');assert len(sources)==3
    assert {(r['stage'],r['part'],r['template']) for r in sources}=={(1,1,7523),(2,0,7524),(3,0,7513)}
    assert all(r['dungeon']==34320 and r['map_quests']==[26650] and r['quests']==[] and r['requires_native_255'] for r in sources)
    assert sum('gate_predecessor' in r for r in sources)==1
    assert next(r for r in sources if r['template']==7513)['gate_predecessor']['template']==7511
    flow=candidate['els_server/domain/dungeon_flow.py']
    queries=[n for n in ast.walk(flow) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='gate_predecessor_blocked']
    assert len(queries)==2
    print(json.dumps(dict(ok=True,source_only=True,source_files=rows,generic95_and_original_story_functions_preserved=True,
        private_sources=3,predecessor_queries=2,runtime_validation=False,SQL=False,native=False,natural=False,
        all_member_SQL_positive=False,group_material_loot=False)))

if __name__=='__main__':main()
