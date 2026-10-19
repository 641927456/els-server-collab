"""Native ice-heater bag migration preserves prior grants and equipped costumes."""
import json,sqlite3,sys,tempfile,uuid
from contextlib import closing
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from inventory_state import InventoryState,InventoryFull
from reward_state import RewardState
from fashion_state import move_fashion
import struct
with tempfile.TemporaryDirectory() as d:
 path=Path(d)/'save.sqlite3';rewards=RewardState(path);store=InventoryState(path);run=str(uuid.uuid4())
 plan=[dict(template=t,metadata=0,group=27,quantity=1) for t in (81020,81021,81025)]
 rewards.grant(run,b'fashion seed',0,0,lambda _:b'ok',item_plan=plan)
 move_fashion(path,struct.pack('>BiBiB',27,2,9,0,0));original=store.snapshot()
 with closing(sqlite3.connect(path)) as db,db:
  # Recreate the old experiment's misclassification, including immutable receipts.
  db.execute('UPDATE inventory_items SET bag_group=7 WHERE bag_group=27')
  grant=json.loads(db.execute('SELECT grant_json FROM reward_receipts WHERE run_id=?',(run,)).fetchone()[0])
  for i in grant['items']:i['group']=7
  db.execute('UPDATE reward_receipts SET grant_json=? WHERE run_id=?',(json.dumps(grant),run))
  items=json.loads(db.execute('SELECT items_json FROM reward_inventory_receipts WHERE run_id=?',(run,)).fetchone()[0])
  for i in items:i['group']=7
  db.execute('UPDATE reward_inventory_receipts SET items_json=? WHERE run_id=?',(json.dumps(items),run))
  receipts=db.execute('SELECT * FROM reward_receipts').fetchall();sequence=db.execute('SELECT * FROM inventory_sequence').fetchall()
 assert InventoryState(path).snapshot()==original
 assert InventoryState(path).snapshot()==original
 with closing(sqlite3.connect(path)) as db:
  assert db.execute('SELECT * FROM reward_receipts').fetchall()==receipts and db.execute('SELECT * FROM inventory_sequence').fetchall()==sequence
  audit=json.loads(db.execute("SELECT audit_json FROM inventory_migrations WHERE name='ice-heater-fashion-native-bag-27-v1'").fetchone()[0]);assert len(audit['changes'])==2
 assert rewards.grant(run,b'fashion seed',0,0,lambda _:b'bad',item_plan=plan)['replayed']
 assert store.snapshot()==original
 # Full corrected bag rejects migration and does not lose the old item.
 full=Path(d)/'full.sqlite3';r=RewardState(full);InventoryState(full)
 r.grant(str(uuid.uuid4()),b'full',0,0,lambda _:b'ok',item_plan=[dict(template=81021,metadata=0,group=27,quantity=36)])
 with closing(sqlite3.connect(full)) as db,db:db.execute('INSERT INTO inventory_items VALUES (999,1001,81025,0,1,7,0)')
 try:InventoryState(full)
 except InventoryFull:pass
 else:raise AssertionError('Full fashion migration accepted')
 with closing(sqlite3.connect(full)) as db:assert db.execute('SELECT bag_group,slot FROM inventory_items WHERE uid=999').fetchone()==(7,0)
print('PASS: native fashion bag migration, equipped preservation, unchanged receipts/UIDs, replay and full-bag rollback.')
