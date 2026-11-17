"""Classify the exact delta against the actual V80 parent, without opening player stores."""
from pathlib import Path
import hashlib,json
W=Path(__file__).resolve().parent
read=lambda p:json.loads(Path(p).read_bytes())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
raw=read(W/'schema-delta.json');assert raw['ok']
removed=raw['removed_literal_definitions'];added=raw['added_literal_definitions']
assert len(removed)==1 and {d['name']for d in removed[0]['definitions']}=={'native_guild_members'}
names=lambda r:{d['name']for d in r['definitions']}
changed=[r for r in added if names(r)=={'native_guild_members'}]
transient=[r for r in added if names(r)=={'native_guild_members_upgrade'}]
assert len(changed)==len(transient)==1
assert 'CHECK(grade BETWEEN 1 AND 6)'in changed[0]['sql']
p=Path(raw['source'])/'els_server/storage/guild_membership_state.py';s=p.read_bytes().decode('utf8')
assert 'INSERT INTO native_guild_members_upgrade SELECT * FROM native_guild_members'in s
assert 'ALTER TABLE native_guild_members_upgrade RENAME TO native_guild_members'in s
assert 'if not db.in_transaction:'in s
persistent=[r for r in added if r not in changed and r not in transient]
tables=sorted({d['name']for r in persistent for d in r['definitions']})
assert len(tables)==15 and not raw['new_indexes']
result=dict(raw,raw_literal_delta=str(W/'schema-delta.json'),raw_literal_delta_sha256=sha(W/'schema-delta.json'),
    added_literal_definitions=persistent,removed_literal_definitions=[],
    changed_literal_definitions=[dict(old=removed[0],new=changed[0],activation='next actual guild mutation in its existing SQL transaction')],
    transient_literal_definitions=transient,new_schema_definitions=15,new_tables=tables,new_indexes=[],
    startup_schema_names=[],startup_DDL_statements=0,startup_index_definitions=0,
    lazy_schema_names=tables,required_native_QA_schema_names=['native_guild_system_v2','native_guild_operations_v2','native_guild_currency_entries_v2'],
    transient_schema_names=['native_guild_members_upgrade'],migration_source_sha256=sha(p),
    migration_preserves_rows='INSERT SELECT within existing caller transaction, then rename',
    related_legacy_upgrade_proof=str(W/'economy-tls-1793884994192432700.json'),publication_executed=False)
(W/'schema-planning.json').write_bytes((json.dumps(result,indent=2)+'\n').encode('utf8'))
print(json.dumps(dict(ok=True,new_persistent_tables=15,changed_existing_tables=1,transient_tables=1,startup_DDL=0)))
