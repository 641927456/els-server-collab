"""Three owned accounts for Hero/Force entry and persisted festival return."""
from pathlib import Path
from contextlib import closing
import sqlite3,struct
POTIONS=(130165,77060,130467,78928)
BOOKS=(295707,295712,300550,295734)

def enroll(row,index,path,operation):
 if index==3:
  from power_fixture import enroll as power_enroll
  return power_enroll(row,index,path,operation)
 from els_server.storage.characters import Characters
 from els_server.storage.local_state import LocalState
 from els_server.storage.reward_state import RewardState
 from els_server.storage.inventory_state import grant_items
 from els_server.storage.quick_slots import save_request,encode,empty
 from els_server.domain.quick_bindings import item_binding
 from els_server.game_data import client_data
 name='Q200'+format(row['account_id'],'x');uid=Characters(path,row['account_id']).create(name,1,operation+':'+str(index))['uid']
 RewardState(path,uid,account_id=row['account_id']);LocalState(path,uid).save(20000,0,0,(1.,2.,3.))
 with closing(sqlite3.connect(path,timeout=60))as db,db:
  db.execute('BEGIN IMMEDIATE')
  assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()==(row['account_id'],)
  db.execute('UPDATE characters SET unit_class=150,level=99,transcendence=1,master=0 WHERE uid=?',(uid,))
  db.execute('UPDATE reward_balances SET ed=1000,experience=? WHERE uid=?',(client_data().thresholds[98],uid))
  if index<2:
   grant_items(db,[dict(template=t,metadata=2,quantity=30,group=6)for t in POTIONS],uid)
   books=grant_items(db,[dict(template=t,metadata=0,quantity=1,group=4)for t in BOOKS],uid)
   row['book_uids']=[item['uid']for item in books]
 if index<2:save_request(path,struct.pack('>i',1)+encode({**empty(),**{i:item_binding(t)for i,t in enumerate(POTIONS)}}),uid)
 row.update(uid=uid,unit=1,target=150,town=20000,character_name=name,scenario='hero_force'if index<2 else'festival',index=index)

def cold(rows,path,*,retired=False):
 from els_server.storage.festival_origins import saved
 from els_server.storage.boosting_2026_force_equipment import snapshot as slots
 from els_server.storage.local_state import LocalState
 result=[]
 with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=60))as db:
  db.execute('PRAGMA query_only=ON')
  for row in rows[:3]:
   uid=row['uid'];assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()==(row['account_id'],)
   assert db.execute('SELECT unit_type,unit_class,level,transcendence FROM characters WHERE uid=?',(uid,)).fetchone()==(1,150,99,1)
   assert db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()==(1000,)
   if row['scenario']=='hero_force':
    counts=dict(db.execute('SELECT template,sum(count) FROM inventory_items WHERE owner=? AND bag_group=6 GROUP BY template',(uid,)))
    assert [counts[t]for t in POTIONS]==[29,30,30,30]
    assert slots(path,uid)==((900401,3),)+((0,0),)*10
    assert db.execute('SELECT count(*) FROM consumable_uses WHERE owner=?',(uid,)).fetchone()==(1,)
    result.append(dict(scenario='hero_force',potion_debit=1,force_removed_in_dungeon=True,ED=1000))
   else:
    expected=20000 if retired else 1503
    assert LocalState(path,uid).load()['map']==expected
    assert saved(db,uid,row['account_id'])==(None if retired else 20000)
    result.append(dict(scenario='festival',map=expected,persisted_source=not retired,source_cleared_after_return=retired,ED=1000))
 from power_fixture import cold as power_cold
 if len(rows)>3:result.append(power_cold(rows[3],path,retired=retired))
 return dict(ok=True,read_only=True,retired=retired,roles=result)
