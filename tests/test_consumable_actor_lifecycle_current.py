"""New three-module guard risks only; no prior fourteen-route reruns."""
import ast,hashlib,json,sqlite3,struct,sys,tempfile,time,unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
from els_server.storage import decomposition,fixed_cubes,ice_state
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.storage.character_selection import save
from els_server.storage.character_lifecycle import change,DAY
ROWS=[]
def wire(uid,choices=()):return struct.pack('>QBBBI',uid,0,0,0,len(choices))+b''.join(struct.pack('>i',t)for t in choices)+struct.pack('>i',0)
class Check(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='pending-consumables-');self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'game.sqlite3'
  self.account=LocalAccount(LocalState(self.path));self.account.enable_characters();self.now=int(time.time())
 def grant(self,t,q=1):
  with closing(sqlite3.connect(self.path))as db,db:
   db.execute('BEGIN IMMEDIATE');return grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=q)],1001)[0]
 def dump(self):
  with closing(sqlite3.connect(self.path))as db:return tuple(db.iterdump())
 def actions(self):
  gear=self.grant(30160);cube=self.grant(130172,3);selected=self.grant(723602,3);ice=self.grant(800000,3)
  return [('decompose',lambda new:decomposition.decompose(self.path,1001,struct.pack('>IQB',1,gear['uid'],0),'decompose-new'if new else'decompose-old')),
   ('fixed-cube',lambda new:fixed_cubes.open_cube(self.path,1001,130172,wire(cube['uid']),'fixed-new'if new else'fixed-old')),
   ('selected-cube',lambda new:fixed_cubes.open_cube(self.path,1001,723602,wire(selected['uid'],(710313,)),'selected-new'if new else'selected-old')),
   ('ice',lambda new:ice_state.draw(self.path,wire(ice['uid']),'ice-new'if new else'ice-old',randbelow=lambda n:0))]
 def test_active_pending_replay_restore_finalized_cold(self):
  actions=self.actions()
  for label,fn in actions:fn(False);ROWS.append(dict(label=label,stage='active',passed=True))
  save(self.path,1,[],[1001])
  with patch('els_server.storage.character_lifecycle.current_time',return_value=self.now):change(self.path,1,1001,'schedule')
  for label,fn in actions:
   for new in (False,True):
    before=self.dump()
    with self.assertRaisesRegex(ValueError,'Item actor is pending deletion or finalized'):fn(new)
    self.assertEqual(self.dump(),before);ROWS.append(dict(label=label,stage='pending',operation='new'if new else'receipt',SQL_zero=True))
  with patch('els_server.storage.character_lifecycle.current_time',return_value=self.now+DAY+1):change(self.path,1,1001,'restore')
  before=self.dump()
  for label,fn in actions:fn(False);self.assertEqual(self.dump(),before);ROWS.append(dict(label=label,stage='restored-receipt',SQL_zero=True))
  cold=LocalAccount(LocalState(self.path));cold.enable_characters()
  with closing(sqlite3.connect(self.path))as db:
   self.assertEqual(cold.get_inventory_snapshot()['items'],load_items(db,1001));self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
  ROWS.append(dict(label='cold-read-FK',passed=True))
  with patch('els_server.storage.character_lifecycle.current_time',return_value=self.now+2*DAY+2):change(self.path,1,1001,'schedule')
  with patch('els_server.storage.character_lifecycle.current_time',return_value=self.now+5*DAY+3):change(self.path,1,1001,'finalize')
  for label,fn in actions:
   for new in (False,True):
    before=self.dump()
    with self.assertRaisesRegex(ValueError,'Item actor is pending deletion or finalized'):fn(new)
    self.assertEqual(self.dump(),before);ROWS.append(dict(label=label,stage='finalized',operation='new'if new else'receipt',SQL_zero=True))
 def test_legacy_optional_lifecycle_and_each_encoder_rollback(self):
  # A genuine old single-role LocalState has no lifecycle/characters table.
  self.path=Path(self.tmp.name)/'legacy.sqlite3';account=LocalAccount(LocalState(self.path));account.enable_inventory()
  with closing(sqlite3.connect(self.path))as db:self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='character_lifecycle'").fetchone())
  actions=self.actions()
  for label,fn in actions:fn(False);ROWS.append(dict(label=label,stage='legacy-without-lifecycle',passed=True))
  gear=self.grant(30160);cube=self.grant(130172);ice=self.grant(800000)
  injected=ValueError('private encoder failure')
  cases=[('decompose',decomposition,'decompose_ack',lambda:decomposition.decompose(self.path,1001,struct.pack('>IQB',1,gear['uid'],0),'rollback-decompose')),
   ('fixed-cube',fixed_cubes,'result',lambda:fixed_cubes.open_cube(self.path,1001,130172,wire(cube['uid']),'rollback-fixed')),
   ('ice',ice_state,'result_events',lambda:ice_state.draw(self.path,wire(ice['uid']),'rollback-ice',randbelow=lambda n:0))]
  for label,module,symbol,fn in cases:
   before=self.dump()
   with patch.object(module,symbol,side_effect=injected):
    with self.assertRaisesRegex(ValueError,'private encoder failure'):fn()
   self.assertEqual(self.dump(),before);ROWS.append(dict(label=label,stage='encoder-rollback',SQL_zero=True))

if __name__=='__main__':unittest.main()
