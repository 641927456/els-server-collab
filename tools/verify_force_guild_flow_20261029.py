"""Preserve the actual parent while verifying the finite Force/GuildAgit delta."""
from pathlib import Path
import ast
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.materialize_formal_runtime import plan

RID='native-force-guild-flow-20261029-v1'
F=ROOT/'references'/RID
read=lambda p:json.loads(p.read_bytes())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
NEW={'els_server/domain/guild_agit_flow.py','els_server/domain/guild_bank_rules.py',
     'els_server/protocol/guild_agit_messages.py','els_server/protocol/guild_bank_capacity_messages.py',
     'els_server/protocol/guild_bank_transfer_messages.py','els_server/storage/guild_bank_capacity.py',
     'els_server/storage/guild_bank_items.py'}

def verify():
    delta=read(F/'delta.json');meta=read(F/'manifest.json')
    assert sha(ROOT/delta['parent_profile'])==delta['parent_profile_sha256']
    parent=read(ROOT/delta['parent_profile']);candidate=read(ROOT/delta['candidate_profile'])
    assert candidate['source_issue']==616 and candidate['delta_business_files']==21
    assert candidate['new_modules']==7 and candidate['new_files']==7
    assert candidate['candidate'] is True and candidate['actual_dual_delivery_verified'] is False
    assert 'acceptance' not in candidate and 'source_PR' not in candidate
    assert meta['issue']==616 and meta['delta_files_per_channel']==21
    assert meta['existing_files_per_channel']==14 and meta['new_modules_per_channel']==7
    assert all(meta[k]==0 for k in ('client_changes','new_hooks','install_DDL'))
    assert not meta['natural_GUI'] and not meta['natural_battle'] and not meta['player_database_restore']
    for channel in ('online','local'):
        before={r['path']:r for r in parent['channels'][channel]['files']}
        after={r['path']:r for r in candidate['channels'][channel]['files']}
        changes=delta['channels'][channel]
        assert len(changes)==21 and set(after)==set(before)|NEW
        assert {name for name in after if after[name]!=before.get(name)}==set(changes)
        for name,row in changes.items():
            assert name.startswith('els_server/') and name.endswith('.py')
            assert row['before_sha256']==before.get(name,{}).get('sha256')
            raw=(ROOT/row['source']).read_bytes()
            assert hashlib.sha256(raw).hexdigest()==row['sha256']==after[name]['sha256']
            assert len(raw)==row['size']==after[name]['size']
            assert row['source']==after[name]['source']
            ast.parse(raw)
            if name in NEW:
                assert row['before_source'] is None
            else:
                assert row['before_source']==before[name]['source']
                assert sha(ROOT/row['before_source'])==row['before_sha256']
        # All locked assets and unchanged sources use the original plan,
        # including source path, size, digest and mode-specific differences.
        plan(ROOT,candidate,channel)
    print(json.dumps({'ok':True,'channels':2,'existing_leaves':14,'new_modules':7,
                      'all_other_parent_entries_preserved':True,'GUI_or_battle_claimed':False}))

if __name__=='__main__':verify()
