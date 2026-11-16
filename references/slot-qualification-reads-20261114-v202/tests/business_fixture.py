"""One owned account matching only the anonymous 16-role slow-request shape."""
from contextlib import closing
import hashlib,json,sqlite3,time
from pathlib import Path
from unittest.mock import patch
SHAPE=json.loads((Path(__file__).with_name('slow-roster-shape.json')).read_bytes())['roles']
def inventory_identity(db,uids):
 rows=db.execute('SELECT * FROM inventory_items WHERE owner IN ('+','.join('?'for _ in uids)+') ORDER BY owner,uid',uids).fetchall()
 return len(rows),hashlib.sha256(repr(rows).encode()).hexdigest()
def enroll(row,index,path,operation):
 from els_server.storage.characters import Characters
 from els_server.storage.local_state import LocalState
 from els_server.storage.seal_quests import QuestState
 from els_server.storage.inventory_state import load_items,grant_items
 from els_server.domain.inventory_items import TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS
 from els_server.game_data import client_data
 assert index==0 and len(SHAPE)==16
 roles=Characters(path,row['account_id']);uids=[];expected=[];now=int(time.time())
 for number,shape in enumerate(SHAPE):
  created_at=now-((15-number)//4)*86400
  # Only this helper process seeds historical owned fixtures. The server's
  # live clock and its normal account/daily limits remain unchanged.
  with patch('els_server.storage.character_lifecycle.current_time',return_value=created_at):
   uid=roles.create('Q202'+format(row['account_id'],'x')+format(number,'x'),shape['unit_type'],operation+':'+str(number))['uid']
  uids.append(uid);QuestState(path,uid,account_id=row['account_id']).snapshot()
  LocalState(path,uid).save(20000,0,0,(1.,2.,3.))
  with closing(sqlite3.connect(path,timeout=60))as db,db:
   db.execute('UPDATE characters SET unit_class=?,level=?,transcendence=?,master=?,revision=revision+1 WHERE uid=?',(shape['unit_class'],shape['level'],shape['transcendence'],shape['master'],uid))
   db.execute('UPDATE reward_balances SET experience=?,ed=1000 WHERE uid=?',(client_data().thresholds[shape['level']-1],uid))
   if shape['master']:db.execute('INSERT INTO character_artifacts VALUES(?,?,?,?,?,?)',(uid,shape['unit_type'],1,1,0,json.dumps([0]*4)))
   db.execute('CREATE TABLE IF NOT EXISTS character_skill_seals (owner INTEGER NOT NULL REFERENCES characters(uid), seal_group INTEGER NOT NULL CHECK(seal_group BETWEEN 1 AND 11), PRIMARY KEY(owner,seal_group))')
   db.executemany('INSERT INTO character_skill_seals VALUES(?,?)',((uid,group)for group in shape['skill_seal_groups']))
   items=load_items(db,uid);count=shape['items']-len(items)
   if count>0:
    item=next(i for i in items if TEMPLATE_BAG_GROUPS[i['template']]in(7,27)and TEMPLATE_MAX_STACKS[i['template']]==1)
    grant_items(db,[dict(template=item['template'],metadata=item['metadata'],group=TEMPLATE_BAG_GROUPS[item['template']],quantity=count)],uid)
   assert len(load_items(db,uid))==shape['items']
   expected.append(dict(uid=uid,unit=shape['unit_type'],career=shape['unit_class'],level=shape['level'],transcendence=shape['transcendence'],master=shape['master'],seals=shape['skill_seal_groups']))
 with closing(sqlite3.connect(path))as db:count,digest=inventory_identity(db,uids)
 row.update(uid=uids[0],unit=SHAPE[0]['unit_type'],town=20000,scenario='sixteen_role_slot_qualification',index=0,role_uids=uids,expected_roles=expected,inventory_count=count,inventory_sha256=digest)
def cold(rows,path,*,retired=False):
 from els_server.storage.local_state import LocalState
 assert len(rows)==1;row=rows[0];uids=row['role_uids']
 with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=60))as db:
  db.execute('PRAGMA query_only=ON')
  assert db.execute('SELECT uid FROM character_owners WHERE account_id=? ORDER BY uid',(row['account_id'],)).fetchall()==[(uid,)for uid in sorted(uids)]
  assert inventory_identity(db,uids)==(row['inventory_count'],row['inventory_sha256'])
  for role in row['expected_roles']:
   uid=role['uid'];assert db.execute('SELECT unit_type,unit_class,level,transcendence,master FROM characters WHERE uid=?',(uid,)).fetchone()==tuple(role[key]for key in('unit','career','level','transcendence','master'))
   assert db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()==(1000,)
   assert [r[0]for r in db.execute('SELECT seal_group FROM character_skill_seals WHERE owner=? ORDER BY seal_group',(uid,))]==role['seals']
   assert LocalState(path,uid).load()['map']==20000
 return dict(ok=True,read_only=True,retired=retired,roles=[dict(roles=16,inventory_count=row['inventory_count'],inventory_unchanged=True,careers_levels_and_seals_unchanged=True,ED_unchanged=True)])
