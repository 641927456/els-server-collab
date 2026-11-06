"""Verify the isolated drop fix without rewriting accepted engine profiles."""
from pathlib import Path
import ast,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.materialize_formal_runtime import bound,verify

def main():
    ref=ROOT/'references/ground-drop-models-20261101-v1'
    contract=json.loads((ref/'source-contract.json').read_bytes())
    assert contract['format']==1 and contract['candidate'] is True
    assert contract['activation'] is False and contract['actual_dual_delivery_verified'] is False
    expected={'els_server/domain/'+name+'.py' for name in ('ground_currency','drop_pickup',
        'dungeon_flow','dungeon_equipment_loot_flow','friends_material_loot','reward_rules',
        'hunter_chest_flow','hunter_chest_rules')}
    assert {row['path']for row in contract['files']}==expected and len(contract['files'])==8
    for row in contract['files']:
        assert row['source']=='references/ground-drop-models-20261101-v1/source/'+row['path']
        source=bound(ROOT,row['source']);verify(source,row);ast.parse(source.read_bytes())
        before=bound(ROOT,row['path'])
        if row['before_sha256'] is None:assert not before.exists()
        else:assert hashlib.sha256(before.read_bytes()).hexdigest()==row['before_sha256']
    print(json.dumps(dict(ok=True,candidate_files=8,historical_inputs_preserved=True,activation=False)))

if __name__=='__main__':main()
