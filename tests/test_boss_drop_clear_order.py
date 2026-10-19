"""Boss pickup before/after clear must coexist with the single clear reward."""
import json,struct,sys,tempfile,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from local_session import LocalSession,LocalAccount
from local_state import LocalState
from protocol_codec import Event
from drop_pickup import potion_pickup_request
from inventory_items import inventory_payload
from els_server.domain.drop_pickup import DROP_ID_XOR
body=bytes.fromhex(json.loads((ROOT/'analysis/client-6c6b5180/20261013-160720/death-event-header.json').read_text(encoding='utf8'))[0]['payload'])
snapshot=json.loads((ROOT/'analysis/client-6c6b5180/20261014-002737/world-drop-probe-snapshot.json').read_text(encoding='utf8'))
wire=bytes.fromhex(next(e['payload_hex'] for e in snapshot['server'] if e.get('event')=='decoded_client_event' and e.get('kind')==208))
decoded=potion_pickup_request(wire)
args=dict(enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True,drop_probe=True,drop_test=True)
for pickup_first in (True,False):
 with tempfile.TemporaryDirectory() as directory:
  account=LocalAccount(LocalState(Path(directory)/'save.sqlite3'));s=LocalSession(account,**args)
  s.role='game';s.phase='dungeon_active';s.gate_stage=2;s.dungeon_substage_synced=True;s.reward_run_id=str(uuid.uuid4())
  b=bytearray(body);struct.pack_into('>i',b,0,0);struct.pack_into('>f',b,46,5000);struct.pack_into('>3f',b,33,*decoded['drop_xyz'])
  death=Event(0x202,performers=(0,),kind=0xad,payload=bytes(b))
  assert [e.kind for e in s.handle(death)]==[0xae,0xaf,0xcf,0xba]
  assert account.get_inventory_snapshot()['items']==[]
  coin=struct.pack('>I',127010)+wire[4:]
  pickup=Event(0x202,performers=(0,),kind=0xd0,payload=coin);clear=Event(0x202,kind=0xbb,payload=b'\0')
  if pickup_first:assert [e.kind for e in s.handle(pickup)]==[0xd1,0xd2]
  replies=s.handle(clear);assert [e.kind for e in replies]==[0xbc,0xd3,0xc1]
  assert replies[1].payload==inventory_payload(s.reward_receipt['items'])
  if not pickup_first:assert [e.kind for e in s.handle(pickup)]==[0xd1,0xd2]
  saved=account.get_inventory_snapshot();assert saved['items'][0]['count']==3 and saved['items'][0]['group']==6
  assert saved['balances']=={'ed':170,'experience':50,'revision':2}
  assert [e.kind for e in s.handle(death)]==[0xae]
  assert [e.kind for e in s.handle(clear)]==[0xbc]
  retry=s.handle(pickup);assert [e.kind for e in retry]==[0xd1]
  assert account.get_inventory_snapshot()==saved
  assert LocalAccount(LocalState(Path(directory)/'save.sqlite3')).get_inventory_snapshot()==saved
print('PASS: Boss ED pickup before/after C1, clear items precede C1, duplicate deaths/clear/pickup do not repeat awards.')
