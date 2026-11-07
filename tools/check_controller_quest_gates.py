"""Portable source contract for the exact installed Laby/Noah retirement increment."""
from pathlib import Path
import ast,hashlib,json
ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=ROOT/'references/controller-quest-gates-20261101-v1'
EXPECTED={(34240,1,0,7407,1),(34250,0,1,7428,1),(34260,1,3,7449,1),(34300,0,1,7500,1),(34300,3,0,7502,2),
    (34600,2,0,8025,3),(34620,0,0,8058,3),(34620,1,0,8059,2),(34680,0,0,8142,9),(34680,0,1,8142,10),(34680,1,0,8142,5)}

def key(row):
    return row['dungeon'],row['stage'],row['part'],row['template'],row['source']['source_index']

def literal_rules(path):
    """Read literal data without importing runtime code or evaluating calls."""
    result=None
    for node in ast.parse(path.read_text('utf8')).body:
        if isinstance(node,ast.Expr)and isinstance(node.value,ast.Constant)and isinstance(node.value.value,str):continue
        if isinstance(node,ast.Assign)and len(node.targets)==1 and isinstance(node.targets[0],ast.Name)and node.targets[0].id=='RULES':
            assert result is None;result=ast.literal_eval(node.value);continue
        if(isinstance(node,ast.Expr)and isinstance(node.value,ast.Call)and isinstance(node.value.func,ast.Attribute)
            and isinstance(node.value.func.value,ast.Name)and node.value.func.value.id=='RULES'
            and node.value.func.attr=='append'and len(node.value.args)==1 and not node.value.keywords):
            assert result is not None;result.append(ast.literal_eval(node.value.args[0]));continue
        raise AssertionError('Unexpected executable source in literal controller rules')
    assert isinstance(result,list)
    return result

def check():
    manifest=json.loads((ARCHIVE/'manifest.json').read_bytes());assert manifest['issue']==729
    assert len(manifest['files'])==1
    for row in manifest['files']:
        raw=(ROOT/row['source']).read_bytes();assert len(raw)==row['size']and hashlib.sha256(raw).hexdigest()==row['sha256']
    for field in('cases','qualification'):
        row=manifest[field];assert hashlib.sha256((ROOT/row['path']).read_bytes()).hexdigest()==row['sha256']
    parent=ROOT/manifest['parent_source'];assert hashlib.sha256(parent.read_bytes()).hexdigest()==manifest['parent_sha256']
    original=literal_rules(parent);updated=literal_rules(ROOT/manifest['files'][0]['source']);cases=json.loads((ROOT/manifest['cases']['path']).read_bytes())
    assert len(original)==135 and updated[:len(original)]==original
    added=updated[len(original):];keys=[key(r)for r in added]
    assert len(keys)==len(set(keys))==11 and set(keys)==EXPECTED
    assert {key(r)for r in cases}==EXPECTED and {key(r):r for r in added}=={key(r):r for r in cases}
    assert not EXPECTED&{key(r)for r in original}
    for r in added:
        assert r['unit']in(13,14)and not r['quests']and r['map_quests']
        assert r['quest_independent']is True and r['requires_native_255']is True
        assert r['template']==r['source']['template']and r['source']['team']==1 and not r['source']['ally']
        assert all(len(r[k])==64 and all(c in'0123456789abcdef'for c in r[k])for k in('graph_sha','script_sha'))
    q=json.loads((ROOT/manifest['qualification']['path']).read_bytes())
    assert q['source_sha256']==manifest['files'][0]['sha256']and q['positions']==11 and q['dungeons']==7
    assert q['online_installed']and q['local_installed']and q['online_observation_seconds']>=120 and q['local_observation_seconds']>=120
    assert q['Application_SQLite_checkpoint_cases']==22 and q['cold_readback_and_duplicate_record_check']
    assert q['natural_GUI']is False and q['natural_battle']is False
    print(json.dumps(dict(ok=True,positions=11,maps=7,unchanged_parent_rules=135,exact_installed_source=True,private_runtime_required=False)))

if __name__=='__main__':check()
