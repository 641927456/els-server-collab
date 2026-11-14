"""Two owned roles: a 35-level Noah purchase and finite collection changes."""
from contextlib import closing
from pathlib import Path
import sqlite3,hashlib,json
TOWN=20000
def native_class(unit,line,stage):
 from els_server.domain.el_search_collection import classes
 return next(c for c,r in classes().items()if(r['unit_type'],r['line'],r['job_stage'])==(unit,line,stage))
def change_ticket(target):
 from els_server.domain.careers import RULES
 return next(t for t,r in RULES.items()if r['target']==target and r['kind']=='class_change')
def enroll(row,index,path,operation):
 from els_server.storage.characters import Characters
 from els_server.storage.local_state import LocalState
 from els_server.storage.reward_state import RewardState
 from els_server.storage.inventory_state import grant_items
 from els_server.storage.ep_points import credit
 from els_server.game_data import client_data
 if index==2:
  name='T199'+format(row['account_id'],'x');uid=Characters(path,row['account_id']).create(name,15,operation+':tutorial')['uid']
  RewardState(path,uid,account_id=row['account_id'])
  with closing(sqlite3.connect(path))as db:
   inventory=db.execute('SELECT uid,template,metadata,count,bag_group,slot FROM inventory_items WHERE owner=? ORDER BY uid',(uid,)).fetchall()
   row.update(uid=uid,unit=15,town=TOWN,character_name=name,scenario='tutorial',target=db.execute('SELECT unit_class FROM characters WHERE uid=?',(uid,)).fetchone()[0],tutorial_balances=list(db.execute('SELECT ed,experience FROM reward_balances WHERE uid=?',(uid,)).fetchone()),tutorial_inventory_sha256=hashlib.sha256(json.dumps(inventory,separators=(',',':')).encode()).hexdigest())
  return
 name='Q199'+format(row['account_id'],'x');unit=14 if index==0 else 1
 uid=Characters(path,row['account_id']).create(name,unit,operation+':'+str(index))['uid']
 RewardState(path,uid,account_id=row['account_id']);LocalState(path,uid).save(TOWN,0,0,(1.,2.,3.))
 initial=142 if index==0 else native_class(1,1,3);level=35 if index==0 else 99
 with closing(sqlite3.connect(path,timeout=60))as db,db:
  db.execute('BEGIN IMMEDIATE')
  assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()==(row['account_id'],)
  db.execute('UPDATE characters SET unit_class=?,level=?,transcendence=? WHERE uid=?',(initial,level,int(index==1),uid))
  db.execute('UPDATE reward_balances SET ed=1000,experience=? WHERE uid=?',(client_data().thresholds[level-1],uid))
  if index==1:
   credit(db,uid,500)
   targets=[native_class(1,line,3)for line in (2,3)];tickets=[change_ticket(t)for t in targets]
   items=grant_items(db,[dict(template=t,metadata=0,group=4,quantity=1)for t in tickets],uid)
   row.update(targets=targets,tickets=tickets,item_uids=[i['uid']for i in items])
 row.update(uid=uid,unit=unit,town=TOWN,character_name=name,scenario='Noah'if index==0 else'collection',target=140 if index==0 else targets[-1])
def cold(rows,path,*,retired=False):
 from els_server.storage.el_search_collection import snapshot,exists
 from els_server.domain.el_search_collection import entry
 from els_server.storage.ep_points import balance
 proof=[]
 with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=60))as db:
  db.execute('PRAGMA query_only=ON')
  for row in rows:
   uid=row['uid'];assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()==(row['account_id'],)
   assert db.execute('SELECT unit_type,unit_class FROM characters WHERE uid=?',(uid,)).fetchone()==(row['unit'],row['target'])
   if row['scenario']=='tutorial':
    assert db.execute('SELECT unit_type,unit_class,level FROM characters WHERE uid=?',(uid,)).fetchone()==(15,row['target'],1)
    assert list(db.execute('SELECT ed,experience FROM reward_balances WHERE uid=?',(uid,)).fetchone())==row['tutorial_balances']
    inventory=db.execute('SELECT uid,template,metadata,count,bag_group,slot FROM inventory_items WHERE owner=? ORDER BY uid',(uid,)).fetchall()
    assert hashlib.sha256(json.dumps(inventory,separators=(',',':')).encode()).hexdigest()==row['tutorial_inventory_sha256']
    proof.append(dict(scenario='tutorial',unit_type=15,level=1,economy_unchanged=True));continue
   expected_ed=950 if row['scenario']=='Noah'else 1000
   assert db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()==(expected_ed,)
   if row['scenario']=='collection':
    value=snapshot(db,uid,row['account_id']);assert value['active']and value['registered']==[entry(row['target'],1)]and value['presets']=={1:{}}
    assert balance(db,uid)==0 and value['expansion']==0 and value['expiry']==0
    assert db.execute('SELECT count(*) FROM inventory_items WHERE uid IN (?,?)',row['item_uids']).fetchone()==(0,)
    assert db.execute('SELECT selection_json FROM character_collection_synergy_slots WHERE owner=?',(uid,)).fetchone()==('[]',)
    if exists(db,'account_search_collection_registration'):
     assert db.execute('SELECT count(*) FROM account_search_collection_registration WHERE account_id=?',(row['account_id'],)).fetchone()==(0,)
   proof.append(dict(scenario=row['scenario'],unit_type=row['unit'],unit_class=row['target'],ED=expected_ed,current_career_contribution_only=row['scenario']=='collection'))
 return dict(ok=True,read_only=True,retired=retired,roles=proof)
