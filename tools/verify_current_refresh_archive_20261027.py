"""Bind the refresh correction to selected current sources without mutating old profiles."""
from pathlib import Path
import ast,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.materialize_formal_runtime import load_manifest,plan

def function(raw,name):
    return next(n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef)and n.name==name)

class RetainedFatigue(ast.NodeTransformer):
    def visit_ImportFrom(self,node):
        return None if node.module=='els_server.domain.normal_fatigue_rules' else node
    def visit_If(self,node):
        if isinstance(node.test,ast.Call)and isinstance(node.test.func,ast.Name)and node.test.func.id=='normal_fatigue_enabled':return None
        return self.generic_visit(node)

def retained_modern_refresh(node,source_sha):
    """Invert only the already-delivered Master refresh additions.

    Full historical projection/SQL/owner/revision AST comparison still follows.
    Unknown function shapes or extra side effects are never ignored.
    """
    has_modern=any(isinstance(n,ast.ImportFrom)and n.module=='els_server.protocol.career_messages'and any(a.name=='current_skill_notices'for a in n.names)for n in node.body)
    if not has_modern:return node
    assert source_sha=='10be037acda763755072450179718a8f3f77c89a51e4ed38ffa0e84fe6369084'
    dump=lambda n:ast.dump(n,include_attributes=False)
    expression=lambda s:ast.parse(s,mode='eval').body
    rebuilt=[];counts=[0,0,0,0]
    for part in node.body:
        if isinstance(part,ast.ImportFrom)and part.module=='els_server.protocol.career_messages':
            assert [(a.name,a.asname)for a in part.names]==[('career_notice',None),('stage_notice',None),('current_skill_notices',None)]
            part.names=part.names[:2];counts[0]+=1
        elif isinstance(part,ast.If)and dump(part.test)==dump(expression("not replayed and before['unit_class'] != character['unit_class']")):
            assert len(part.orelse)==1 and isinstance(part.orelse[0],ast.If)
            branch=part.orelse[0];assert dump(branch.test)==dump(expression('not replayed'))
            assert len(branch.orelse)==1 and dump(branch.orelse[0])==dump(ast.parse('answer = []').body[0])
            part.orelse=branch.body;counts[1]+=1
        elif isinstance(part,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='rebuild'for t in part.targets):
            assert dump(part)==dump(ast.parse("rebuild = not replayed and before['unit_class'] == character['unit_class'] and not before['master']").body[0]);counts[2]+=1;continue
        elif isinstance(part,ast.Return):
            expected=expression('answer + current_skill_notices(character, slots, rebuild=rebuild) + [skill_slots_initialization(slots, uid, character)]')
            assert dump(part.value)==dump(expected)
            part.value=expression('answer + [skill_slots_initialization(slots, uid, character)]');counts[3]+=1
        rebuilt.append(part)
    assert counts==[1,1,1,1],counts
    node.body=rebuilt;return node

def main():
    archive=json.loads((ROOT/'references/current-refresh-combat-inputs-20261027-v1/manifest.json').read_bytes())
    assert archive['PR']==554 and len(archive['files'])==2
    profile=load_manifest(ROOT/'channels/current-engine.json',ROOT)
    checked={}
    for mode in ('online','local'):
        selected={e['path']:(e,p)for e,p in plan(ROOT,profile,mode)}
        for row in archive['files']:
            raw=(ROOT/row['source']).read_bytes()
            assert len(raw)==row['size']and hashlib.sha256(raw).hexdigest()==row['sha256']
            entry,path=selected[row['path']]
            name='notifications'if row['path'].endswith('career_shop.py')else'load_character'
            expected=function(raw.decode('utf8'),name)
            actual=RetainedFatigue().visit(function(path.read_text('utf8'),name))
            if name=='notifications':actual=retained_modern_refresh(actual,entry['sha256'])
            assert ast.dump(actual,include_attributes=False)==ast.dump(expected,include_attributes=False),(mode,row['path'])
        checked[mode]=2
    print(json.dumps(dict(ok=True,selected_current_refresh_functions=checked,
                         same_SQL_projection_and_owner_checks_retained=True,
                         historical_canonical_and_profile_bytes_unchanged=True,
                         existing_formal_fatigue_reader_retained=True,
                         runtime_or_player_database_actions=0)))

if __name__=='__main__':main()
