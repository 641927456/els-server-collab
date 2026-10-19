"""Original Boss clear and original town/end requests synchronize saved inventory."""
import json,sqlite3,struct,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from local_session import LocalSession,LocalAccount
from local_state import LocalState
from protocol_codec import Event
from dungeon_population import population
from inventory_items import inventory_payload
from local_messages import character_unit
body=bytes.fromhex(json.loads((ROOT/'analysis/client-6c6b5180/20261013-160720/death-event-header.json').read_text(encoding='utf8'))[0]['payload'])
entry=bytes.fromhex('eefc726aad751f003e6b6d2e0c4d36e2923600000010332b6d21282a5c1774790f0f3a4c7947')
def death(n):
 b=bytearray(body);struct.pack_into('>i',b,0,n['key']);struct.pack_into('>f',b,46,n['hp']);return Event(0x202,performers=(0,),kind=0xad,payload=bytes(b))
args={'enter_town':True,'enter_dungeon':True,'client_build':'dx11_260923','npc_slot_test':True,'gate_test':True,'population_test':True,'clear_test':True,'reward_test':True,'item_test':True}
with tempfile.TemporaryDirectory() as d:
 path=Path(d)/'save.sqlite3';account=LocalAccount(LocalState(path));s=LocalSession(account,**args);s.role='game';s.phase='town_ready'
 s.handle(Event(0x202,kind=0x7d4,payload=struct.pack('>ii',1,30000)));s.handle(Event(0x202,kind=0x382,payload=entry));s.handle(Event(0x202,kind=0x91,payload=struct.pack('>ii',100,0)))
 bb=Event(0x202,kind=0xbb,payload=b'\0')
 for stage in range(3):
  s.handle(Event(0x202,kind=0xb3,payload=bytes(9)))
  assert account.get_inventory_snapshot()['items']==[]
  p=population(stage)
  for n in p['npcs']:
   if n['active'] or n['key']==p['clear_key']:s.handle(death(n))
  reply=s.handle(bb)
 assert [e.kind for e in reply]==[0xbc,0xd3,0xc1] and s.reward_receipt['items'][0]['count']==3
 assert reply[1].payload==inventory_payload(s.reward_receipt['items'])
 assert s.clear_items_synced
 snap=account.get_inventory_snapshot();assert snap['balances']=={'ed':120,'experience':50,'revision':1} and len(snap['items'])==1
 assert [e.kind for e in s.handle(bb)]==[0xbc] and account.get_inventory_snapshot()==snap
 returned=s.handle(Event(0x202,kind=0x225,payload=struct.pack('>i',20000)+b'\0'))
 expected=character_unit(account.get_location(),True,account.get_skills(),snap['balances'])+inventory_payload([])+bytes(5)
 assert [e.kind for e in returned]==[0xd9,0x226] and returned[0].payload==expected
 # Re-login restoration emits one original full sync after scene readiness.
 reopened=LocalAccount(LocalState(path));r=LocalSession(reopened,**args);r.role='game';r.phase='map_loading'
 r.handle(Event(0x202,kind=0x225,payload=struct.pack('>i',20000)+b'\0'))
 ready=Event(0x202,kind=0x227,payload=struct.pack('>fffBH',0,0,0,0,0))
 assert [e.kind for e in r.handle(ready)]==[0x228,0xd9]
 assert [e.kind for e in r.handle(ready)]==[0x228] and reopened.get_inventory_snapshot()==snap
 # An early original reason72 end must preserve already saved items/money.
 r.phase='dungeon_active';ended=r.handle(Event(0x202,kind=0x67,payload=struct.pack('>i',0x72)+bytes(96)))
 assert [e.kind for e in ended]==[0x68,0xd9] and ended[1].payload==r.saved_user_sync().payload and reopened.get_inventory_snapshot()==snap
 try:LocalSession(reopened,item_test=True)
 except ValueError:pass
 else:raise AssertionError('Unisolated inventory profile accepted')
print('PASS: actual stage/Boss gates issue D3 before C1, return is state-only, saved login/early return preserve inventory.')
