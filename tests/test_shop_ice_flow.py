"""Buying a stack, using it and replaying either operation conserve inventory."""
import json,sqlite3,struct,sys,tempfile
from contextlib import closing
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_session import LocalAccount,LocalSession
from local_state import LocalState
from inventory_state import load_items
from shop_state import catalog,purchase
from ice_state import draw,POOL
from ice_messages import result_events
from tools.install_ed_shop_bridge import bridge_source
args=dict(enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True,shop_test=True,ice_test=True)
with tempfile.TemporaryDirectory() as directory:
 path=Path(directory)/'flow.sqlite3';account=LocalAccount(LocalState(path));session=LocalSession(account,**args)
 with closing(sqlite3.connect(path)) as db,db:db.execute('UPDATE reward_balances SET ed=100 WHERE uid=1001')
 offer=next(p for p in catalog() if p['template']==800000);assert offer['price']==30
 buy=struct.pack('>IIH',1,offer['sku'],2)
 response=purchase(path,buy,'buy');assert purchase(path,buy,'buy')==response
 with closing(sqlite3.connect(path)) as db:
  items=load_items(db);assert len(items)==1
  item=items[0];assert (item['template'],item['group'],item['count'])==(800000,4,2)
  assert db.execute('SELECT ed FROM reward_balances').fetchone()[0]==40
 use=struct.pack('>QBBBIi',item['uid'],0,0,0,0,0)
 result=draw(path,use,'draw',randbelow=lambda _:0)
 assert draw(path,use,'draw',randbelow=lambda _:1/0)==result
 events=result_events(result);assert [e.kind for e in events]==[0xad8,0x197]
 assert events[0].payload==result[24:-15]
 assert purchase(path,buy,'buy')==response
 with closing(sqlite3.connect(path)) as db:
  assert next(i for i in load_items(db) if i['uid']==item['uid'])['count']==1
  assert sum(i['count'] for i in load_items(db) if i['template']==POOL[0][0])==1
  assert db.execute('SELECT ed,revision FROM reward_balances').fetchone()==(40,2)
  assert db.execute('SELECT COUNT(*) FROM shop_purchase_receipts').fetchone()[0]==1
  assert db.execute('SELECT COUNT(*) FROM ice_draw_receipts').fetchone()[0]==1
image=(Path(__file__).resolve().parents[1]/'analysis/client-6c6b5180/x2-runtime.bin').read_bytes()
source=bridge_source(image);assert '__ED_ROLE_DATA__' not in source and 'ebRoleData[type].size' in source
assert '"size": '+str(5+28*len(catalog(5))) in source
print('PASS: purchase-to-draw stack conservation, independent replay, ED/revision receipts and dynamic native catalog size.')
