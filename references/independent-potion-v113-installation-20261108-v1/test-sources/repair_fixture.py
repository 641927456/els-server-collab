"""Synthetic supply only for a fresh, durably enrolled owned QA identity."""
from contextlib import closing
from pathlib import Path
import hashlib,json,sqlite3,struct,uuid

def seed_role_experience(path,uid,account_id,operation):
 from els_server.storage.reward_state import RewardState
 from els_server.storage.characters import Characters
 from els_server.game_data import client_data
 proof=json.dumps(dict(operation=operation,uid=uid,account_id=account_id,purpose='synthetic owned potion qualification at level cap'),sort_keys=True).encode()
 run_id=str(uuid.uuid5(uuid.NAMESPACE_URL,operation+':owned-potion-level:'+str(uid)))
 store=RewardState(path,uid,account_id=account_id);before=store.balances();experience=client_data().thresholds[98]-before['experience'];assert experience>0
 store.grant(run_id,proof,0,experience,response_builder=lambda b:struct.pack('>Q',b['experience']))
 assert Characters(path,account_id).get(uid)['level']==99
 return dict(synthetic_owned_QA_experience=True,normal_reward_writer=True,level=99,proof_sha256=hashlib.sha256(proof).hexdigest())

def snapshot(path,values):
 assert len(values)==1;uid=values[0]['uid']
 with closing(sqlite3.connect(Path(path).as_uri()+'?mode=ro',uri=True))as db:
  db.execute('BEGIN')
  count=db.execute('SELECT COALESCE(SUM(count),0)FROM inventory_items WHERE owner=?AND template=130165',(uid,)).fetchone()[0]
  exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name='consumable_uses'").fetchone()
  receipts=db.execute('SELECT COUNT(*)FROM consumable_uses WHERE owner=?',(uid,)).fetchone()[0]if exists else 0
 return dict(count=count,receipts=receipts)

def supply_owned(path,accounts_file,work,operation,values):
 assert len(values)==1;value=values[0];work=Path(work)
 proof=json.loads((work/'owned-account-enrollment.private.json').read_bytes())
 assert proof['version']==1 and proof['operation']==operation and Path(proof['accounts_file']).resolve()==Path(accounts_file).resolve()
 targets=[t for t in proof['targets']if t['id']==value['account_id']];assert len(targets)==1;target=targets[0]
 assert target['name']==value['bridge']['name']and target['token_hash']==hashlib.sha256(value['bridge']['token'].encode()).hexdigest()
 with closing(sqlite3.connect(Path(accounts_file).as_uri()+'?mode=ro',uri=True))as db:
  assert db.execute('SELECT id,name,token_hash,enabled FROM accounts WHERE id=?',(target['id'],)).fetchone()==(target['id'],target['name'],target['token_hash'],1)
 from els_server.storage.characters import Characters
 character=Characters(path,value['account_id']).get(value['uid'])
 assert character['name']==value['character_name']and character['unit_type']==value['unit_type']
 assert snapshot(path,values)==dict(count=0,receipts=0)
 experience=seed_role_experience(path,value['uid'],value['account_id'],operation)
 from els_server.storage.inventory_state import grant_items
 from els_server.storage.quick_slots import empty,save_request
 from els_server.domain.quick_bindings import item_binding
 with closing(sqlite3.connect(path))as db,db:
  db.execute('BEGIN IMMEDIATE');grant_items(db,[dict(template=130165,metadata=2,group=6,quantity=10)],value['uid'])
 slots=empty();slots[0]=item_binding(130165)
 save_request(path,struct.pack('>iI',1,len(slots))+b''.join(struct.pack('>ii',k,v)for k,v in slots.items()),value['uid'])
 assert snapshot(path,values)==dict(count=10,receipts=0)
 result=dict(ok=True,synthetic_owned_QA_supply=True,quantity=10,template=130165,normal_inventory_writer=True,experience_fixture=experience)
 (work/'owned-potion-fixture.json').write_bytes((json.dumps(result,indent=2)+'\n').encode());return result
