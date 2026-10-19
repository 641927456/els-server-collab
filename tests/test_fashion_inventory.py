"""Fashion copies have distinct UIDs; retries/full bags cannot duplicate or lose them."""
import sqlite3,sys,tempfile,uuid,struct
from pathlib import Path
from contextlib import closing
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from inventory_items import fashion_catalog,inventory_payload,item_body,validate_item
from inventory_state import InventoryState,InventoryFull
from reward_state import RewardState

with tempfile.TemporaryDirectory() as directory:
 path=Path(directory)/'fashion.sqlite3';rewards=RewardState(path);inventory=InventoryState(path)
 run=str(uuid.uuid4());plan=[{'template':81021,'metadata':0,'quantity':2,'group':27}]
 a=rewards.grant(run,b'fashion test',0,0,lambda _:b'fashion',item_plan=plan)
 items=inventory.snapshot()['items'];assert len(items)==2
 assert {i['count'] for i in items}=={1} and len({i['uid'] for i in items})==2
 assert {i['slot'] for i in items}=={0,1} and {i['group'] for i in items}=={27}
 assert struct.unpack('>IBi',item_body(items[0])[:9])==(81021,0,1)
 assert rewards.grant(run,b'fashion test',0,0,lambda _:b'bad',item_plan=plan)['replayed']
 assert InventoryState(path).snapshot()['items']==items
 try:validate_item({**items[0],'count':2})
 except ValueError:pass
 else:raise AssertionError('Fashion stacking accepted')
 # Both bag categories use independent slots and capacity.
 for template,metadata,group,quantity in [(81021,0,27,34),(77000,2,6,99)]:
  rewards.grant(str(uuid.uuid4()),b'fill',0,0,lambda _:b'ok',item_plan=[dict(template=template,metadata=metadata,group=group,quantity=quantity)])
 before=inventory.snapshot();assert len(before['items'])==37
 assert len(inventory_payload(before['items']))==4+37*324
 with closing(sqlite3.connect(path)) as db:sequence=db.execute('SELECT next_uid FROM inventory_sequence').fetchone()[0]
 try:rewards.grant(str(uuid.uuid4()),b'full fashion bag',50,10,lambda _:b'ok',item_plan=plan)
 except InventoryFull:pass
 else:raise AssertionError('Fashion bag overfill accepted')
 assert inventory.snapshot()==before
 with closing(sqlite3.connect(path)) as db:assert db.execute('SELECT next_uid FROM inventory_sequence').fetchone()[0]==sequence
 assert len(fashion_catalog()['templates'])==12
print('PASS: nonstackable fashion UIDs, native item header, durable replay, separate bags and atomic full-bag rollback.')
