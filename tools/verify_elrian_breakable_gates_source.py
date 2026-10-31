"""Verify the installed source archive without private runtime assets."""
import ast
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=ROOT/'references/elrian-breakable-gates-20261101-v1'

def rules(path):
    result=[]
    tree=ast.parse(path.read_text('utf8'))
    for node in tree.body:
        if isinstance(node,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='RULES'for t in node.targets):
            result.extend(ast.literal_eval(node.value))
        elif(isinstance(node,ast.Expr)and isinstance(node.value,ast.Call)
             and isinstance(node.value.func,ast.Attribute)and node.value.func.attr=='append'
             and isinstance(node.value.func.value,ast.Name)and node.value.func.value.id=='RULES'):
            result.append(ast.literal_eval(node.value.args[0]))
    return result

def main():
    manifest=json.loads((ARCHIVE/'source-contract.json').read_bytes())
    assert len(manifest['files'])==3
    assert hashlib.sha256((ARCHIVE/'repair.patch').read_bytes()).hexdigest()==manifest['repair_patch_sha256']
    for row in manifest['files']:
        path=ARCHIVE/row['source']
        assert path.stat().st_size==row['size']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256']
        assert hashlib.sha256((ARCHIVE/'parent'/row['path']).read_bytes()).hexdigest()==row['parent_sha256']
        compile(path.read_text('utf8'),str(path),'exec')
    parent=rules(ARCHIVE/'parent/els_server/domain/public_controller_rules.py')
    candidate=rules(ARCHIVE/'source/els_server/domain/public_controller_rules.py')
    assert len(parent)==len(candidate)
    changed=[]
    for before,after in zip(parent,candidate):
        if before!=after:
            assert after==dict(before,allow_combat_death=True)
            assert after['requires_native_255']and after['requires_no_active_hostiles']
            changed.append((after['dungeon'],after['stage'],after['part'],after['template']))
    assert changed==[(34060,1,0,6212),(34060,2,1,6213)]
    # Script-only Labyrinth doors remain meaningful negative cases.
    labyrinth=[r for r in candidate if r['dungeon']==34090 and r['template']in(6506,6507)]
    assert len(labyrinth)==5 and all(r['requires_native_255']and not r.get('allow_combat_death')for r in labyrinth)
    summary=json.loads((ARCHIVE/'qualification.json').read_bytes())
    assert summary['dual_installed']and summary['public_TLS_gate6212_to_stage2']and summary['public_TLS_gate6213_to_stage3']
    assert summary['public_premature_gate_refused']and not summary['natural_GUI']
    print('Elrian gates: three exact source leaves, two breakable gates, five native-only negatives; installed protocol evidence bound.')

if __name__=='__main__':main()
