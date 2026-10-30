"""Bind candidate outputs while preserving historical materializer inputs."""
import hashlib
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.materialize_formal_runtime import bound,verify


def main():
    contract=json.loads((ROOT/'references/weapon-growth-ui-20261031-v1/source-contract.json').read_bytes())
    assert contract['format']==1 and contract['candidate'] is True
    assert contract['activation'] is False and contract['runtime_acceptance'] is False
    rows=contract['files'];assert len(rows)==12 and len({r['path'] for r in rows})==12
    archived={'els_server/domain/raid_economy_flow.py':'dc27ade1a5b309e7c0df368627249f0c0a067ce70cbebe1cf48cd9e53f3a5835',
              'els_server/protocol/quest_messages.py':'deab46e729df0a774c3f4f23bb15d481630c9d7832aeec1d614054e3228cbfba'}
    historical=dict(archived)
    archived['els_server/domain/inventory_items.py']=None
    assert set(contract['archived_outputs'])==set(archived)
    for row in rows:
        expected=('references/weapon-growth-ui-20261031-v1/source/'+row['path']
                  if row['path'] in archived else row['path'])
        assert row['source']==expected
        path=bound(ROOT,row['source']);verify(path,row)
        if path.suffix=='.py':compile(path.read_text('utf-8-sig'),row['path'],'exec')
    for name,digest in historical.items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest
    integrated=contract['integrated_inventory']
    assert hashlib.sha256((ROOT/integrated['path']).read_bytes()).hexdigest()==integrated['sha256']
    print(json.dumps(dict(ok=True,candidate_outputs=12,historical_inputs_preserved=2,
        activation=False,runtime_execution=False)))


if __name__=='__main__':main()
