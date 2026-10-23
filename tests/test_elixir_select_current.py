"""New box source caps/merge/full-bag risks; original guarded transaction."""
from els_server.storage import fixed_cubes as cube
from pathlib import Path
import tempfile,sqlite3,json,struct,unittest
from contextlib import closing
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items,InventoryFull
from els_server.storage.bag_capacity import allowances
ROWS=[]
def req(uid,choice):return struct.pack('>QBBBIii',uid,0,0,0,1,choice,0)
class Storage(unittest.TestCase):
 def test_exact_stack_caps_merge_full_rollback_and_current_retry(self):
  with tempfile.TemporaryDirectory(prefix='elixir-box-private-')as tmp:
   path=Path(tmp)/'game.sqlite3';account=LocalAccount(LocalState(path));account.enable_characters()
   def grant(t,n):
    with closing(sqlite3.connect(path))as db,db:return grant_items(db,[dict(template=t,metadata=0 if t==723603 else 2,group=4,quantity=n)],1001)[0]
   def rows():
    with closing(sqlite3.connect(path))as db:return load_items(db,1001)
   def dump():
    with closing(sqlite3.connect(path))as db:return tuple(db.iterdump())
   original=grant(710206,98);box=grant(723603,2)
   response=cube.open_cube(path,1001,723603,req(box['uid'],710206),'merge99')
   self.assertEqual([i['count']for i in rows()if i['template']==710206],[99,4]);self.assertEqual(sum(i['count']for i in rows()if i['template']==723603),1)
   grant(723603,1)
   with closing(sqlite3.connect(path))as db:capacity=allowances(db,1001)[4]
   while sum(i['group']==4 for i in rows())<capacity:grant(710207,99)
   before=dump()
   with self.assertRaises(InventoryFull):cube.open_cube(path,1001,723603,req(box['uid'],710210),'full')
   self.assertEqual(before,dump())
   retry=cube.open_cube(path,1001,723603,req(box['uid'],710206),'merge99')
   self.assertEqual(before,dump());self.assertEqual([e.kind for e in retry],[0x105,0x197])
   with closing(sqlite3.connect(path))as db:
    self.assertEqual(db.execute('SELECT count(*) FROM inventory_action_receipts WHERE operation_id=?',('merge99',)).fetchone()[0],1)
    self.assertFalse(db.execute("SELECT 1 FROM sqlite_master WHERE name IN ('world_elixir_state','world_elixir_uses')").fetchone())
    self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
   ROWS.append(dict(case='723603-source99-output99-98plus5splits99and4-fullgroup4-zero-write-current-retry-one-receipt',passed=True,capacity=capacity,new_schema=False,world_business_not_imported=True))
if __name__=='__main__':unittest.main()
