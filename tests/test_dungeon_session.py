"""Experimental entry ordering must not mutate the durable town/skills state."""
import sys,struct,tempfile
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from local_session import LocalSession,LocalAccount
from local_state import LocalState
from protocol_codec import Event

recorded=bytes.fromhex('eefc726aad751f003e6b6d2e0c4d36e2923600000010332b6d21282a5c1774790f0f3a4c7947')
with tempfile.TemporaryDirectory(prefix='dungeon-test-',dir=BASE/'analysis') as folder:
 store=LocalState(Path(folder)/'local.sqlite3');account=LocalAccount(store)
 original=(store.load(),store.load_layout(),store.load_bindings(),store.load_skills())
 s=LocalSession(account,True,True);s.role='game';s.phase='town_ready'
 ack=s.handle(Event(0x202,kind=0x382,payload=recorded))[0]
 assert ack.kind==0x383 and ack.payload[:4]==b'\xff'*4
 for bad in (b'',bytes(7),struct.pack('>ii',1,30050),struct.pack('>ii',2,30000)):
  assert struct.unpack_from('>i',s.handle(Event(0x202,kind=0x7d4,payload=bad))[0].payload)[0] in (817,1406)
 assert s.handle(Event(0x202,kind=0x7d4,payload=struct.pack('>ii',1,30000)))[0].payload==struct.pack('>ii',0,1)
 for bad in (recorded[:-1],recorded+b'\0',recorded[:18]+bytes(4)+recorded[22:]):
  assert s.handle(Event(0x202,kind=0x382,payload=bad))[0].payload[:4]==b'\xff'*4
 result=s.handle(Event(0x202,kind=0x382,payload=recorded));assert [e.kind for e in result]==[0x383,0x14a]
 assert s.phase=='dungeon_loading'
 for progress in (0,10,30,80,100):
  reply=s.handle(Event(0x202,kind=0x91,payload=struct.pack('>ii',progress,0)))
  assert [e.kind for e in reply]==([0x92,0x93,0x96,0xb2] if progress==100 else [0x92,0x93])
  assert reply[0].payload==struct.pack('>iiI',0,progress,0)
  assert reply[1].payload==struct.pack('>Qi',1001,progress)
 assert s.phase=='dungeon_active'
 for bad in (b'',bytes(8),bytes(10),b'\1'+bytes(8),bytes(5)+struct.pack('>f',-1),bytes(5)+struct.pack('>f',float('nan'))):
  assert s.handle(Event(0x202,kind=0xb3,payload=bad))==[]
 completion=s.handle(Event(0x202,kind=0xb3,payload=bytes(9)))
 assert [e.kind for e in completion]==[0xb4,0xb5,0xb6,0xb7,0xbd]
 assert completion[0].payload==struct.pack('>i',0)
 assert completion[1].payload==struct.pack('>iQ',0,1001)
 assert completion[2].payload==bytes(16)
 assert completion[3].payload==b'\0'
 assert completion[4].payload==bytes(7)+struct.pack('>i',-1)
 assert all(e.kind not in (0x68,0xd9) for e in completion)
 assert [e.kind for e in s.handle(Event(0x202,kind=0xb3,payload=bytes(9)))]==[0xb4,0xb5]
 assert [e.kind for e in s.handle(Event(0x202,kind=0xb3,payload=bytes.fromhex('000000000040b66666')))]==[0xb4,0xb5]
 premature=LocalSession(account,True,True);premature.role='game';premature.phase='dungeon_loading'
 assert premature.handle(Event(0x202,kind=0xb3,payload=bytes(9)))==[]
 assert [e.kind for e in s.handle(Event(0x202,kind=0x91,payload=struct.pack('>ii',100,0)))]==[0x92,0x93]
 for bad in (b'',bytes(7),struct.pack('>ii',101,0),struct.pack('>ii',-1,0),struct.pack('>ii',100,1)):
  assert s.handle(Event(0x202,kind=0x91,payload=bad))==[]
 assert s.handle(Event(0x202,kind=0x22b,payload=bytes(30)))==[]
 assert (store.load(),store.load_layout(),store.load_bindings(),store.load_skills())==original
 assert LocalSession(enter_town=True).handle(Event(0x202,kind=0x7d4,payload=bytes(8)))==[]
 for sample in ('000000084c71532d3854463f5ebc842a2f7a408b002cea7fe8091e862dc7','a8200001bc514cb16425e3b9000000096f373d706f0f2b362f59ad449acfb3'):
  s=LocalSession(account,True,True);s.role='game';s.phase='town_ready'
  s.handle(Event(0x202,kind=0x7d4,payload=struct.pack('>ii',1,30000)))
  assert [e.kind for e in s.handle(Event(0x202,kind=0x382,payload=bytes.fromhex(sample)))]==[0x383,0x14a]
print('PASS: entry approval, create ordering, corrupt native request controls, experimental opt-in and town save isolation.')
