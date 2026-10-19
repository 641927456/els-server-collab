"""Correct the known potion classification without awarding or losing items."""
import hashlib,json,sqlite3,sys,tempfile,uuid
from contextlib import closing
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from inventory_items import inventory_payload,validate_item
from inventory_state import InventoryState,ensure_inventory,InventoryFull
from reward_state import RewardState,RewardConflict

def ledger(db):
 return [list(db.execute('SELECT * FROM '+table)) for table in ('reward_balances','reward_receipts','reward_inventory_receipts','inventory_sequence')]

with tempfile.TemporaryDirectory() as directory:
 path=Path(directory)/'legacy.sqlite3';store=RewardState(path);run=str(uuid.uuid4());proof=b'original pickup';plan=[{'template':77000,'metadata':2,'quantity':1,'group':2}]
 old={'uid':1001001,'template':77000,'metadata':2,'count':6,'group':2,'slot':0}
 with closing(sqlite3.connect(path)) as db,db:
  ensure_inventory(db)
  db.execute('INSERT INTO inventory_items VALUES (1001001,1001,77000,2,6,2,0)')
  db.execute('UPDATE inventory_sequence SET next_uid=1001002')
  db.execute('UPDATE reward_balances SET ed=360,experience=150,revision=6')
  db.execute('INSERT INTO reward_receipts VALUES (?,?,?,?,?)',(run,hashlib.sha256(proof).hexdigest(),json.dumps({'ed':0,'experience':0,'items':plan}),b'historical D3',json.dumps({'ed':360,'experience':150,'revision':6})))
  db.execute('INSERT INTO reward_inventory_receipts VALUES (?,?)',(run,json.dumps([old])))
  before=ledger(db)
 snap=InventoryState(path).snapshot();new={**old,'group':6}
 assert snap['items']==[new] and inventory_payload([new])[12]==6
 assert snap['balances']=={'ed':360,'experience':150,'revision':6}
 for _ in range(2):assert InventoryState(path).snapshot()==snap
 with closing(sqlite3.connect(path)) as db:
  assert ledger(db)==before
  audit=json.loads(db.execute('SELECT audit_json FROM inventory_migrations').fetchone()[0])
  assert audit=={'changes':[{'before':old,'after':new}],'receipts_preserved':True}
 retry=store.grant(run,proof,0,0,item_plan=[{**plan[0],'group':6}],inventory_response_builder=lambda *_:(_ for _ in ()).throw(AssertionError('re-encoded')))
 assert retry['replayed'] and retry['items']==[new] and retry['response']==b'historical D3'
 assert InventoryState(path).snapshot()==snap
 try:store.grant(run,proof,0,0,item_plan=[{**plan[0],'group':6,'quantity':2}],inventory_response_builder=lambda *_:b'bad')
 except RewardConflict:pass
 else:raise AssertionError('Migration weakened conflicting retry detection')
 try:validate_item(old)
 except ValueError:pass
 else:raise AssertionError('New potion accepted into accessory bag')

with tempfile.TemporaryDirectory() as directory:
 path=Path(directory)/'collision.sqlite3';RewardState(path)
 with closing(sqlite3.connect(path)) as db,db:
  ensure_inventory(db);db.execute('INSERT INTO inventory_items VALUES (1001001,1001,77000,2,6,2,0)');db.execute('INSERT INTO inventory_items VALUES (1001002,1001,77000,2,8,6,0)')
 assert InventoryState(path).snapshot()['items']==[{'uid':1001002,'template':77000,'metadata':2,'count':8,'group':6,'slot':0},{'uid':1001001,'template':77000,'metadata':2,'count':6,'group':6,'slot':1}]

with tempfile.TemporaryDirectory() as directory:
 path=Path(directory)/'full.sqlite3';RewardState(path)
 with closing(sqlite3.connect(path)) as db,db:
  ensure_inventory(db);db.execute('INSERT INTO inventory_items VALUES (1001001,1001,77000,2,6,2,0)')
  for slot in range(36):db.execute('INSERT INTO inventory_items VALUES (?,1001,77000,2,99,6,?)',(1002000+slot,slot))
 try:InventoryState(path)
 except InventoryFull:pass
 else:raise AssertionError('Full destination bag accepted migration')
 with closing(sqlite3.connect(path)) as db:
  assert db.execute('SELECT bag_group,slot,count FROM inventory_items WHERE uid=1001001').fetchone()==(2,0,6)
  assert db.execute('SELECT COUNT(*) FROM inventory_migrations').fetchone()[0]==0
print('PASS: potion bag correction preserves UID/count/wallet/receipts, is idempotent, preserves replay conflicts and rolls back a full destination.')
