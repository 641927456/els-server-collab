"""Unrelated stackable coupons must not become zero-count result entries."""
import json,sqlite3,struct,sys,tempfile,uuid
from contextlib import closing
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from els_server.domain.local_session import LocalSession,LocalAccount
from els_server.storage.local_state import LocalState
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import character_unit
from els_server.domain.drop_pickup import potion_pickup_request
from els_server.domain.inventory_items import inventory_payload
from els_server.domain.dungeon_drops import potion_pickup_notice,potion_drop_notice

native=json.loads((ROOT/'analysis/skills-clear-20261015/pickup-pair-native.json').read_text())
fixed=next(r for r in native if r['name']=='fixed')
old=next(r for r in native if r['name']=='old')
markers=next(r for r in native if r['name']=='markers')
assert old['tail']==[204,204,52428]  # Old reader left the sentinel untouched.
assert fixed['pair']==[0,0] and fixed['tail']==[0,0,0] and fixed['consumed']==fixed['size']==50
assert markers['pair']==[17,19] and markers['tail']==[7,1,0x1234]
assert struct.unpack('>Qiib?QIQiib?H',potion_pickup_notice(910001,1002).payload)==(1002,77000,910001,0,False,0,1,1002,0,0,0,False,0)

body=bytes.fromhex(json.loads((ROOT/'analysis/client-6c6b5180/20261013-160720/death-event-header.json').read_text())[0]['payload'])
capture=json.loads((ROOT/'analysis/client-6c6b5180/20261014-002737/world-drop-probe-snapshot.json').read_text())
wire=bytes.fromhex(next(e['payload_hex'] for e in capture['server'] if e.get('event')=='decoded_client_event' and e.get('kind')==208))
decoded=potion_pickup_request(wire)
args=dict(enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True,drop_probe=True,drop_test=True)
for pickup_first in (True,False):
 with tempfile.TemporaryDirectory() as directory:
  path=Path(directory)/'save.sqlite3'
  account=LocalAccount(LocalState(path));s=LocalSession(account,**args)
  with closing(sqlite3.connect(path)) as db,db:
   db.execute('INSERT INTO inventory_items VALUES (1001001,1001,274333,2,1,4,0)')
   db.execute('INSERT INTO inventory_items VALUES (1001002,1001,77000,2,98,6,0)')
   db.execute('UPDATE inventory_sequence SET next_uid=1001003')
  s.role='game';s.phase='dungeon_active';s.gate_stage=2;s.dungeon_substage_synced=True;s.reward_run_id=str(uuid.uuid4())
  b=bytearray(body);struct.pack_into('>i',b,0,0);struct.pack_into('>f',b,46,5000);struct.pack_into('>3f',b,33,*decoded['drop_xyz'])
  s.handle(Event(0x202,performers=(0,),kind=0xad,payload=bytes(b)))
  # Keep this regression focused on stack splitting and return deltas. Current
  # boss loot is native food/ED; explicitly issue the legacy potion fixture.
  s.world_drops[910001]={**s.world_drops[910001],'template':77000,'ed':0,
      'payload_hex':potion_drop_notice(910001,decoded['drop_xyz']).payload.hex()}
  pickup=Event(0x202,performers=(0,),kind=0xd0,payload=wire)
  if pickup_first:s.handle(pickup)
  s.handle(Event(0x202,kind=0xbb,payload=b'\0'))
  if not pickup_first:s.handle(pickup)
  snapshot=account.get_inventory_snapshot();potions=[i for i in snapshot['items'] if i['template']==77000]
  assert sum(i['count'] for i in potions)==102
  assert next(i for i in snapshot['items'] if i['template']==274333)['count']==1
  retry=s.handle(pickup)
  pickup_ids={i['uid'] for i in s.pickup_receipt['items']}
  assert retry[-1].payload==inventory_payload([i for i in potions if i['uid'] in pickup_ids])
  returned=s.handle(Event(0x202,kind=0x225,payload=struct.pack('>i',20000)+b'\0'))
  reward_ids={i['uid'] for i in s.reward_receipt['items']}
  expected=character_unit(account.get_location(),True,account.get_skills(),snapshot['balances'],snapshot['items'])+inventory_payload([])+bytes(5)
  assert returned[0].kind==0xd9 and returned[0].payload==expected
  # State-only D9 contains no bag delta; login 2A restores existing items.
  assert s.saved_user_sync().payload==expected
  assert account.get_inventory_snapshot()==snapshot
  assert LocalAccount(LocalState(path)).get_inventory_snapshot()==snapshot
print('PASS: native D2 pair/tail; clear-return and pickup retries exclude unrelated coupons, preserve split stacks/current counts/persistence.')
