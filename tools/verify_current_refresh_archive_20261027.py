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

def verified_Master_successor(profile,mode,row,entry,path,expected):
    """Accept the pinned PR608 notification successor while checking its parent."""
    assert row['path']=='els_server/storage/career_shop.py'
    assert profile.get('actual_dual_delivery_verified')is True
    delta=json.loads((ROOT/'references/native-master-current-skills-20261028-v1-source-v6/delta.json').read_bytes())
    replacement=delta['channels'][mode][row['path']]
    assert replacement['source']==entry['source']and replacement['sha256']==entry['sha256']
    assert hashlib.sha256(path.read_bytes()).hexdigest()==replacement['sha256']
    parent=json.loads((ROOT/delta['parent']).read_bytes())
    prior=next(e for e in parent['channels'][mode]['files']if e['path']==row['path'])
    original=(ROOT/prior['source']).read_bytes()
    assert hashlib.sha256(original).hexdigest()==prior['sha256']==replacement['before_sha256']
    retained=RetainedFatigue().visit(function(original.decode('utf8'),'notifications'))
    assert ast.dump(retained,include_attributes=False)==ast.dump(expected,include_attributes=False)

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
            if ast.dump(actual,include_attributes=False)!=ast.dump(expected,include_attributes=False):
                verified_Master_successor(profile,mode,row,entry,path,expected)
        checked[mode]=2
    print(json.dumps(dict(ok=True,selected_current_refresh_functions=checked,
                         same_SQL_projection_and_owner_checks_retained=True,
                         historical_canonical_and_profile_bytes_unchanged=True,
                         existing_formal_fatigue_reader_retained=True,
                         runtime_or_player_database_actions=0)))

if __name__=='__main__':main()
