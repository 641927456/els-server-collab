"""Series isolation, native categories and transactional draws across new offers."""
import json,sqlite3,struct,sys,tempfile
from contextlib import closing
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from inventory_items import native_ice_catalog,validate_item
from inventory_state import load_items
from local_session import LocalAccount,LocalSession
from local_state import LocalState
from shop_state import catalog,purchase
from ice_state import POOLS,draw
from ice_messages import result_events
c=native_ice_catalog();offers=catalog()
assert len(c['offers'])==272 and len(POOLS)==137
assert len({p['sku'] for p in offers})==len(offers)
assert {p['category'] for p in offers if p['template'] in {r['template'] for r in c['offers']}}=={34}
assert {34,52,53}<={p['category'] for p in offers}
assert not {11,12,13,14,15,16} & {p['category'] for p in offers}
assert {x for x,_ in POOLS[800000]}!={x for x,_ in POOLS[800210]}
with tempfile.TemporaryDirectory() as directory:
 path=Path(directory)/'series.sqlite3';account=LocalAccount(LocalState(path))
 LocalSession(account,enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True,shop_test=True,ice_test=True)
 with closing(sqlite3.connect(path)) as db,db:db.execute('UPDATE reward_balances SET ed=500 WHERE uid=1001')
 for template in (800000,800210,800386):
  offer=next(p for p in offers if p['template']==template)
  wire=struct.pack('>IIH',1,offer['sku'],1)
  bought=purchase(path,wire,'buy-'+str(template));assert purchase(path,wire,'buy-'+str(template))==bought
  with closing(sqlite3.connect(path)) as db,db:item=next(i for i in load_items(db) if i['template']==template)
  use=struct.pack('>QBBBIi',item['uid'],0,0,0,0,0)
  response=draw(path,use,'draw-'+str(template),randbelow=lambda n:n-1)
  assert draw(path,use,'draw-'+str(template),randbelow=lambda n:1/0)==response
  assert [e.kind for e in result_events(response)]==[0xad8,0x197]
  with closing(sqlite3.connect(path)) as db,db:
   row=json.loads(db.execute('SELECT outcome_json FROM ice_draw_receipts WHERE operation_id=?',('draw-'+str(template),)).fetchone()[0])
   assert row['consumed']['template']==template
   assert row['reward'][0]['template']==POOLS[template][-1][0]
   assert all(i['uid']!=item['uid'] for i in load_items(db))
   for i in load_items(db):validate_item(i)
 with closing(sqlite3.connect(path)) as db,db:
  assert db.execute('SELECT ed FROM reward_balances').fetchone()[0]==410
  assert len(load_items(db))==3
print('PASS: native category IDs, 272 unique machines, 137 character-compatible pools, three distinct series, receipt replay, exhausted stack removal and ED conservation.')
