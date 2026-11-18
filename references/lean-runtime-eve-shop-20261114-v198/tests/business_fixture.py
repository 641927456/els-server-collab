"""Two owned Eve roles follow the two ordinary career-shop purchase chains."""
from contextlib import closing
from pathlib import Path
import sqlite3
TOWN=20000
def enroll(row,index,path,operation):
 from els_server.storage.characters import Characters
 from els_server.storage.local_state import LocalState
 from els_server.storage.reward_state import RewardState
 from els_server.game_data import client_data
 name='E198'+format(row['account_id'],'x')
 uid=Characters(path,row['account_id']).create(name,5,operation+':'+str(index))['uid']
 RewardState(path,uid,account_id=row['account_id']);LocalState(path,uid).save(TOWN,0,0,(1.,2.,3.))
 with closing(sqlite3.connect(path,timeout=60))as db,db:
  db.execute('BEGIN IMMEDIATE')
  assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()==(row['account_id'],)
  db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,))
  db.execute('UPDATE reward_balances SET ed=1000,experience=? WHERE uid=?',(client_data().thresholds[98],uid))
 row.update(uid=uid,unit=5,town=TOWN,character_name=name,first=(214490,214500)[index],second=(217970,217980)[index],target=(108,109)[index])
def cold(rows,path,*,retired=False):
 proof=[]
 with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=60))as db:
  db.execute('PRAGMA query_only=ON')
  for row in rows:
   uid=row['uid'];assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()==(row['account_id'],)
   assert db.execute('SELECT unit_type,unit_class FROM characters WHERE uid=?',(uid,)).fetchone()==(5,row['target'])
   assert db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()==(900,)
   assert db.execute('SELECT count(*) FROM inventory_items WHERE owner=? AND template IN (?,?)',(uid,row['first'],row['second'])).fetchone()==(0,)
   proof.append(dict(unit_type=5,unit_class=row['target'],ED=900,career_service_items_remaining=0))
 return dict(ok=True,read_only=True,retired=retired,roles=proof)
