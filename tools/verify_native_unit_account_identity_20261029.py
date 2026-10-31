"""Verify the exact five-source correction and retain every other parent entry."""
from pathlib import Path
import ast,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.materialize_formal_runtime import load_manifest,plan
RID='native-unit-account-identity-20261029-v1'
F=ROOT/'references'/RID
LEAVES={'els_server/storage/characters.py','els_server/storage/seal_quests.py',
        'els_server/storage/career_shop.py','els_server/protocol/local_messages.py',
        'els_server/protocol/dungeon_messages.py'}
read=lambda p:json.loads(p.read_bytes())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def restored(raw,path,rules):
    text=raw.decode('utf-8');newline='\r\n'if b'\r\n'in raw else'\n'
    for old,new in reversed(rules[path]):
        old,new=old.replace('\n',newline),new.replace('\n',newline)
        assert text.count(new)==1,'Exact account-source inverse missing or repeated'
        text=text.replace(new,old,1)
    return text.encode('utf-8')

def verify():
    d=read(F/'delta.json');q=read(F/'qualification.json');rules=read(F/'source-inverse.json')
    assert d['issue']==q['issue']==620 and sha(ROOT/d['parent'])==d['parent_sha256']
    assert sha(F/'source-inverse.json')==q['source_inverse_sha256']
    assert set(rules)==LEAVES
    parent=read(ROOT/d['parent']);candidate=read(ROOT/d['candidate_profile'])
    assert candidate['candidate']is True and candidate['actual_dual_delivery_verified']is False
    assert candidate['source_issue']==620 and candidate['delta_business_files']==5
    assert 'acceptance'not in candidate and 'installed_source_commit'not in candidate
    assert candidate['new_modules']==candidate['new_files']==0
    assert q['changed_existing_files_per_channel']==5 and q['typed_owner_required']
    assert q['new_schema']is False and not q['full_Actor_or_GUI'] and not q['relationship_900_Photo_included']
    assert q['install_DDL']==q['client_changes']==q['new_hooks']==q['new_runtime_modules']==0
    for channel in ('online','local'):
        before={r['path']:r for r in parent['channels'][channel]['files']}
        after={r['path']:r for r in candidate['channels'][channel]['files']}
        changes=d['channels'][channel]
        assert set(changes)==LEAVES and set(after)==set(before)
        assert {p for p in after if after[p]!=before[p]}==LEAVES
        assert candidate['channels'][channel]['parent_release']==d['actual_parent_heads'][channel]['release']
        for path,r in changes.items():
            assert r['before_sha256']==before[path]['sha256']==sha(ROOT/r['before_source'])
            assert r['before_source']==before[path]['source']
            source=ROOT/r['source'];raw=source.read_bytes();ast.parse(raw)
            assert sha(source)==r['sha256']==after[path]['sha256']
            assert len(raw)==r['size']==after[path]['size'] and r['source']==after[path]['source']
            original=restored(raw,path,rules)
            assert original==(ROOT/r['before_source']).read_bytes(),'Nonidentity parent behavior changed'
            assert ast.dump(ast.parse(original))==ast.dump(ast.parse((ROOT/r['before_source']).read_bytes()))
        plan(ROOT,candidate,channel)
    if (F/'accepted-delivery.json').exists():
        receipt=read(F/'accepted-delivery.json')
        accepted=read(ROOT/'channels/native-unit-account-identity-accepted-20261029-v1.json')
        assert receipt['ok'] and receipt['unit_account_identity_delivery_complete']
        assert receipt['own_locks_released'] and not receipt['player_database_restore']
        assert not receipt['natural_GUI'] and not receipt['full_Actor_or_combat']
        assert accepted['candidate']is False and accepted['actual_dual_delivery_verified']is True
        for channel in ('online','local'):
            row=receipt['channels'][channel]
            assert row['observation_seconds']>=120 and row['all_parent_business_bytes_preserved_except_five']
            assert accepted['channels'][channel]['files']==candidate['channels'][channel]['files']
            assert row['business_files']==len(accepted['channels'][channel]['files'])
            assert accepted['accepted_heads'][channel]=={k:row[k]for k in ('release','formal_manifest_sha256')}
            plan(ROOT,accepted,channel)
        # Validate the active accepted selection without pinning future current
        # to this historical release. Later wrappers require their own profile.
        current=load_manifest(ROOT/'channels/current-engine.json',ROOT)
        assert current.get('accepted_heads') and current['candidate']is False
        assert current['actual_dual_delivery_verified']is True
    print(json.dumps(dict(ok=True,existing_sources_per_channel=5,new_modules=0,new_schema=False,
                         client_or_Hook_changes=0,all_other_parent_entries_exact=True,Actor_or_GUI_claimed=False)))

if __name__=='__main__':verify()
