"""Portable source/receipt gate; no private runtime or game process required."""
from pathlib import Path
import ast,hashlib,json
ROOT=Path(__file__).resolve().parents[1]
RID='retained-native-consumable-readers-20261027-v1'
load=lambda p:json.loads(Path(p).read_bytes())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
manifest=load(ROOT/('channels/'+RID+'.json'));delta=load(ROOT/('references/'+RID+'/delta.json'))
parent=load(ROOT/delta['parent']);qualification=load(ROOT/('references/'+RID+'/qualification.json'))
expected={'els_server/data/retained_native_consumables.json','els_server/domain/retained_native_consumables.py','els_server/domain/inventory_items.py','els_server/domain/acquisition_policy.py','els_server/storage/inventory_state.py'}
assert qualification['client_changes']==qualification['new_hooks']==qualification['new_consumers']==qualification['new_sources']==qualification['new_tables']==qualification['install_DDL']==qualification['player_database_migrations']==0
for ch in('online','local'):
 changes=delta['channels'][ch];assert set(changes)==expected
 old={e['path']:e for e in parent['channels'][ch]['files']};new={e['path']:e for e in manifest['channels'][ch]['files']}
 assert set(new)-set(old)=={'els_server/data/retained_native_consumables.json','els_server/domain/retained_native_consumables.py'}
 for rel,e in new.items():
  if rel not in changes:assert e==old[rel]
 for rel,e in changes.items():
  p=ROOT/e['source'];assert p.is_file()and sha(p)==e['sha256']==new[rel]['sha256'];assert (old.get(rel)or{}).get('sha256')==e['before_sha256']
  if p.suffix=='.py':ast.parse(p.read_text('utf8'))
 data=load(ROOT/changes['els_server/data/retained_native_consumables.json']['source']);assert len(data['items'])==39 and len({r['template']for r in data['items']})==39 and not data['new_sources']and not data['consumption_enabled']
 code=(ROOT/changes['els_server/domain/retained_native_consumables.py']['source']).read_text('utf8');tree=ast.parse(code)
 pin=next(n.value.value for n in tree.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='DATA_SHA'for t in n.targets));assert pin==sha(ROOT/changes['els_server/data/retained_native_consumables.json']['source'])
 for row in data['items']:assert(row['item_type'],row['group'])in((5,6),(7,4))and row['metadata']==2 and row['owned_max_stack']==max(row['raw_max_stack'],999)
 checks=[q for q in qualification['private_qualifications']if q['channel']==ch];assert checks
 for q in checks:
  assert q['private_App_transport']and q['first_and_cold_2A']and q['SQL_unchanged']and q['negative_manual_requests']==78 and q['original_machine_code_item_reads']==117
  for p in q['source_pins']:assert changes[p['path']]['sha256']==p['sha256']
routes=load(ROOT/('references/'+RID+'/route-classification.json'));assert len(routes['rows'])==39 and sum(r['route']=='client_registration_required_for_original_quick_drag'for r in routes['rows'])==34
assert all(not r['consumption_enabled']for r in routes['rows'])
print(json.dumps(dict(ok=True,channels=2,runtime_leaves=5,new_consumers=0,client_changes=0,new_hooks=0)))
