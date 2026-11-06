"""Ghost carriage (unit 85) closed loop: shop offer, activation, ride, stamina, cold login."""
import sqlite3,struct,sys,tempfile
from contextlib import closing
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from els_server.storage.reward_state import RewardState
from els_server.storage.inventory_state import InventoryState
from els_server.storage.shop_state import catalog,purchase
from els_server.storage.companion_state import handle as activate,snapshot
from els_server.storage.mount_state import handle as mount,attach,login

STONE=550333
offer=next(p for p in catalog(1) if p['template']==STONE)
assert (offer['category'],offer['price'],offer['quantity'])==(63,50,1)

with tempfile.TemporaryDirectory() as folder:
 path=Path(folder)/'loop.sqlite3';RewardState(path);inventory=InventoryState(path)
 with closing(sqlite3.connect(path)) as db,db:db.execute('UPDATE reward_balances SET ed=1000 WHERE uid=1001')
 request=struct.pack('>IIH',1,offer['sku'],1)
 reply=purchase(path,request,'buy-stone')
 assert purchase(path,request,'buy-stone')==reply
 assert inventory.snapshot()['balances']['ed']==950
 stone=next(i for i in inventory.snapshot()['items'] if i['template']==STONE)
 ack=activate(path,1001,0x432,struct.pack('>Q',stone['uid']),'activate-stone')
 assert struct.unpack_from('>i',ack.payload)[0]==0
 saved=snapshot(path,1001);carriage=next(p for p in saved['companions'] if p['kind']=='mount')
 assert carriage['unit']==85 and carriage['stamina']==120
 with closing(sqlite3.connect(path)) as db:
  assert db.execute('SELECT COUNT(*) FROM inventory_items WHERE template=?',(STONE,)).fetchone()[0]==0
 try:activate(path,1001,0x432,struct.pack('>Q',stone['uid']),'activate-again')
 except ValueError:pass
 else:raise AssertionError('Consumed summon stone activated twice')
 mount(path,1001,0x42c,struct.pack('>QB',carriage['uid'],1),'ride',now=1000)
 mount(path,1001,0x42f,struct.pack('>Qi',carriage['uid'],0),'down',now=1024)
 with closing(sqlite3.connect(path)) as db,db:login(db,1001,now=1024)
 cold=snapshot(path,1001,enter_world=True)
 assert cold['mount']==0 and not cold['mounted']
 assert next(p for p in cold['companions'] if p['uid']==carriage['uid'])['uid']==carriage['uid']
 with closing(sqlite3.connect(path)) as db,db:attach(db,1001,cold['companions'],now=1096)
 assert snapshot(path,1001)['companions'][[p['uid'] for p in snapshot(path,1001)['companions']].index(carriage['uid'])]['stamina']==120
 with closing(sqlite3.connect(path)) as db,db:db.execute('UPDATE reward_balances SET ed=0 WHERE uid=1001')
 with closing(sqlite3.connect(path)) as db:before=db.execute('SELECT COUNT(*) FROM inventory_items').fetchone()[0]
 try:purchase(path,request,'buy-no-money')
 except ValueError:pass
 else:raise AssertionError('Purchase without balance accepted')
 with closing(sqlite3.connect(path)) as db:
  assert db.execute('SELECT COUNT(*) FROM inventory_items').fetchone()[0]==before

with tempfile.TemporaryDirectory() as folder:
 path=Path(folder)/'cap.sqlite3';RewardState(path);InventoryState(path)
 from els_server.domain.inventory_items import VERIFIED_TEMPLATES
 from els_server.storage.inventory_state import grant_items
 with closing(sqlite3.connect(path)) as db,db:
  first=grant_items(db,[dict(template=STONE,metadata=VERIFIED_TEMPLATES[STONE],group=4,quantity=1)])[0]
 activate(path,1001,0x432,struct.pack('>Q',first['uid']),'cap-first')
 with closing(sqlite3.connect(path)) as db,db:
  db.executemany('INSERT INTO companions VALUES (?,?,?,?,?,?)',
                 [(1005000+n,1001,'mount',85,'Fill'+str(n),999) for n in range(999)])
  second=grant_items(db,[dict(template=STONE,metadata=VERIFIED_TEMPLATES[STONE],group=4,quantity=1)])[0]
 try:activate(path,1001,0x432,struct.pack('>Q',second['uid']),'cap-full')
 except ValueError:pass
 else:raise AssertionError('Companion capacity 1000 not enforced')
print('PASS: 550333 shop offer, activation, ride/down stamina and cold-login ownership/state.')
