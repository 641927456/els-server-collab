"""Verify the exact installed leveling source archive without private assets."""
from pathlib import Path
import ast,hashlib,json

ROOT=Path(__file__).resolve().parents[1]
DIRECTORY=ROOT/'references/mainline-leveling-exp20-20261031-v1'

def main():
    contract=json.loads((DIRECTORY/'source-contract.json').read_bytes())
    assert contract['schema']==1 and contract['source_archive_only']
    expected={'els_server/storage/reward_state.py','els_server/domain/formal_pve_economy.py',
              'els_server/data/formal_pve_economy.json','els_server/data/formal_pve_economy.manifest.json'}
    for channel,row in contract['channels'].items():
        assert channel in ('online','local') and row['installed']
        assert {x['path']for x in row['changes']}==expected
        for entry in row['changes']:
            source=ROOT/entry['source'];assert source.resolve().is_relative_to(DIRECTORY.resolve())
            raw=source.read_bytes();assert len(raw)==entry['size']and hashlib.sha256(raw).hexdigest()==entry['sha256']
            if source.suffix=='.py':ast.parse(raw.decode('utf8'))
    assert set(contract['channels'])=={'online','local'}
    source=DIRECTORY/'source/common/els_server/data'
    raw=(source/'formal_pve_economy.json').read_bytes()
    assert json.loads((source/'formal_pve_economy.manifest.json').read_bytes())['payload_sha256']==hashlib.sha256(raw).hexdigest()
    assert json.loads(raw)['local']['leveling_experience_multiplier']==20
    assert all(row['blocked']==0 for row in contract['validation']['progression_budget'])
    public=contract['validation']['public']
    assert public['ok']and public['level']>=7 and public['next30092_allowed']and public['cold_authenticated_restore']
    assert contract['validation']['own_QA_cleaned']and contract['validation']['launcher_selected']
    assert not contract['new_schema']and not contract['player_database_restore']
    print(json.dumps(dict(ok=True,exact_source_files=4,channels=2,ordinary_multiplier=20,actual_runtime_not_started_by_this_check=True)))

if __name__=='__main__':main()
