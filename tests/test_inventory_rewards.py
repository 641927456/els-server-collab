"""ED/EXP and native inventory must commit/replay/roll back as one grant."""
import concurrent.futures,json,sqlite3,sys,tempfile,uuid
from contextlib import closing
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from reward_state import RewardState,RewardConflict
from inventory_state import InventoryState,InventoryFull
from inventory_items import inventory_payload
PLAN=[{'template':77000,'metadata':2,'quantity':3,'group':6}]
with tempfile.TemporaryDirectory() as d:
 path=Path(d)/'state.sqlite3';store=RewardState(path);inventory=InventoryState(path);run=str(uuid.uuid4())
 first=store.grant(run,b'boss proof',120,50,lambda _:b'C1',item_plan=PLAN)
 snap=inventory.snapshot();assert snap['balances']=={'ed':120,'experience':50,'revision':1}
 assert snap['items']==[{'uid':1001001,'template':77000,'metadata':2,'count':3,'group':6,'slot':0}]
 assert len(inventory_payload(snap['items']))==328 and first['items']==snap['items']
 retry=store.grant(run,b'boss proof',120,50,lambda _:(_ for _ in ()).throw(AssertionError('re-encoded')),item_plan=PLAN)
 assert retry['replayed'] and retry['items']==first['items'] and inventory.snapshot()==snap
 second=store.grant(str(uuid.uuid4()),b'boss two',120,50,lambda _:b'C1',item_plan=PLAN)
 assert second['items'][0]['uid']==1001001 and second['items'][0]['count']==6
 assert InventoryState(path).snapshot()['items'][0]['count']==6
 before=inventory.snapshot()
 with closing(sqlite3.connect(path)) as db,db:db.execute("CREATE TRIGGER fail_inventory_receipt BEFORE INSERT ON reward_inventory_receipts BEGIN SELECT RAISE(ABORT,'injected'); END")
 try:store.grant(str(uuid.uuid4()),b'boss three',120,50,lambda _:b'C1',item_plan=PLAN)
 except sqlite3.IntegrityError:pass
 else:raise AssertionError('Inventory receipt failure ignored')
 assert inventory.snapshot()==before
 with closing(sqlite3.connect(path)) as db,db:db.execute('DROP TRIGGER fail_inventory_receipt')
 try:store.grant(run,b'boss proof',120,50,lambda _:b'C1',item_plan=[{**PLAN[0],'quantity':4}])
 except RewardConflict:pass
 else:raise AssertionError('Conflicting inventory retry accepted')
 same=str(uuid.uuid4())
 def grant_retry(_):return store.grant(same,b'concurrent boss',120,50,lambda _:b'C1',item_plan=PLAN)
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(grant_retry,range(8)))
 assert sum(not r['replayed'] for r in results)==1 and inventory.snapshot()['items'][0]['count']==9
 # A full bag must roll back currency, items, receipt and UID allocation.
 with closing(sqlite3.connect(path)) as db,db:
  db.execute('UPDATE inventory_items SET count=99')
  for slot in range(1,36):db.execute('INSERT INTO inventory_items VALUES (?,1001,77000,2,99,6,?)',(1001001+slot,slot))
  db.execute('UPDATE inventory_sequence SET next_uid=1001037')
 before=inventory.snapshot()
 try:store.grant(str(uuid.uuid4()),b'full bag boss',120,50,lambda _:b'C1',item_plan=PLAN)
 except InventoryFull:pass
 else:raise AssertionError('Full bag grant accepted')
 assert inventory.snapshot()==before
 with closing(sqlite3.connect(path)) as db:assert db.execute('SELECT next_uid FROM inventory_sequence').fetchone()[0]==1001037
print('PASS: native item wire, persistent stacking/UIDs, atomic currency+bag receipts, failed/full-bag rollback and concurrent once-only grant.')
