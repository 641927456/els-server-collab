"""Verify exact qualified channel sources without changing selected engines."""
from pathlib import Path
import ast,hashlib,json

ROOT=Path(__file__).resolve().parents[1]


def main():
    contract=ROOT/'references/ordinary-field-passage-20261031-v1/source-contract.json'
    data=json.loads(contract.read_bytes())
    assert data['source_archive_only'] is True and data['passage_only'] is True
    assert data['fields']==24 and data['portal_edges']==76
    assert data['client_changes']==0 and data['new_schema'] is False
    assert data['field_monsters_and_rewards'] is False and data['natural_GUI'] is False
    count=0
    for mode in ('online','local'):
        rows=data['channels'][mode]['changes'];assert len(rows)==12
        assert len({r['path']for r in rows})==12
        for row in rows:
            path=(ROOT/row['source']).resolve()
            assert path.is_relative_to(contract.parent.resolve())
            raw=path.read_bytes();assert len(raw)==row['size']
            assert hashlib.sha256(raw).hexdigest()==row['sha256']
            if path.suffix=='.py':ast.parse(raw)
            else:json.loads(raw)
            count+=1
    print(json.dumps(dict(ok=True,qualified_channel_files=count,selected_engine_changed=False,private_runtime_executed=False)))


if __name__=='__main__':main()
