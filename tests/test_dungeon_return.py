"""Native captured end request: phase/retry/save isolation and next entry."""
import json,struct,sys,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from local_session import LocalSession,LocalAccount
from local_state import LocalState
from protocol_codec import Event
from dungeon_messages import return_user_sync
native=json.loads((root/'analysis/client-6c6b5180/end-request-native.json').read_text())
payload=bytes.fromhex(native['payload_hex'])
assert payload[:4]==struct.pack('>i',0x72)
with tempfile.TemporaryDirectory(dir=root/'analysis') as folder:
 store=LocalState(Path(folder)/'test.sqlite3');account=LocalAccount(store)
 original=(store.load(),store.load_skills(),store.load_layout(),store.load_bindings())
 s=LocalSession(account,True,True,'dx11_260923');s.role='game';s.phase='dungeon_active';s.dungeon_substage_synced=True
 for bad in (b'',payload[:40],struct.pack('>i',0x71)+payload[4:],payload+bytes(8192)):
  assert s.handle(Event(0x202,kind=0x67,payload=bad))==[] and s.phase=='dungeon_active'
 result=s.handle(Event(0x202,kind=0x67,payload=payload))
 assert [r.kind for r in result]==[0x68,0xd9] and result[0].payload==bytes(31)
 assert result[1].payload==return_user_sync(account.get_location(),account.get_skills()).payload and len(result[1].payload)==1030
 assert s.phase=='map_loading' and s.pending_map is None
 assert [r.kind for r in s.handle(Event(0x202,kind=0x67,payload=payload))]==[0x68]
 assert s.handle(Event(0x202,kind=0x67,payload=payload+b'\0'))==[]
 assert (store.load(),store.load_skills(),store.load_layout(),store.load_bindings())==original
 assert s.handle(Event(0x202,kind=0x225,payload=struct.pack('>iB',20000,0)))[0].kind==0x226
 assert s.handle(Event(0x202,kind=0x227,payload=struct.pack('>fffBH',1,2,3,0,20)))[0].kind==0x228
 assert s.phase=='town_ready' and store.load()['map']==20000
 s.handle(Event(0x202,kind=0x7d4,payload=struct.pack('>ii',1,30000)))
 create=bytes.fromhex('eefc726aad751f003e6b6d2e0c4d36e2923600000010332b6d21282a5c1774790f0f3a4c7947')
 assert [r.kind for r in s.handle(Event(0x202,kind=0x382,payload=create))]==[0x383,0x14a]
 assert s.phase=='dungeon_loading' and not s.dungeon_substage_synced and s.dungeon_end_payload is None
 legacy=LocalSession(account,True,True);legacy.role='game';legacy.phase='dungeon_active'
 assert legacy.handle(Event(0x202,kind=0x67,payload=payload))==[]
print('PASS: native end ACK/user sync, duplicate end, town return phases, save isolation and second entry reset.')
