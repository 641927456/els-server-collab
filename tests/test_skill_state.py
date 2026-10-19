"""Native skill equip shape, swaps, transaction replay and state isolation."""
import struct,sys,tempfile,json
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from skill_state import DEFAULT_SLOTS,encode_slots,decode_slots,equip_request,initialization_payload
from local_state import LocalState
from local_session import LocalAccount,LocalSession
from protocol_codec import Event

assert len(initialization_payload())==296
assert initialization_payload()[13:17]==struct.pack('>I',22)
assert decode_slots(encode_slots(DEFAULT_SLOTS))==DEFAULT_SLOTS
with tempfile.TemporaryDirectory(prefix='skills-test-',dir=BASE/'analysis') as folder:
 path=Path(folder)/'local.sqlite3';store=LocalState(path)
 location=store.load();layout=store.load_layout();keys=store.load_bindings()
 s=LocalSession(LocalAccount(store),True);s.role='game';s.phase='town_ready'
 def request(index,skill):return s.handle(Event(0x202,kind=0x122,payload=struct.pack('>ii',index,skill)))[0]
 ack=request(2,21200);assert ack.kind==0x123
 assert struct.unpack('>5i',ack.payload)==(0,2,21200,1,0)
 assert LocalAccount(LocalState(path)).get_skills()[:4]==(21000,0,21200,0)
 request(2,21200)
 with store.connect() as db:assert db.execute('SELECT revision FROM skill_slots').fetchone()[0]==1
 assert struct.unpack('>5i',request(0,21200).payload)==(0,0,21200,2,21000)
 assert store.load_skills()[:4]==(21200,0,21000,0)
 saved=store.load_skills()
 for payload in (b'',bytes(7),bytes(9),struct.pack('>ii',-1,21000),struct.pack('>ii',5,21000),struct.pack('>ii',0,21001),struct.pack('>ii',0,21026)):
  result=s.handle(Event(0x202,kind=0x122,payload=payload))[0]
  assert struct.unpack('>i',result.payload[:4])[0]==-1 and store.load_skills()==saved
 assert store.load()==location and store.load_layout()==layout and store.load_bindings()==keys
 request(2,0);request(1,21000)
 assert store.load_skills()[:4]==(21200,21000,0,0)
 new=LocalSession(enter_town=True)
 assert new.handle(Event(0x202,kind=0x122,payload=bytes(8)))==[]
 s.phase='characters_ready'
 initialized=s.handle(Event(0x202,kind=0x28,payload=struct.pack('>Q',1001)))
 assert next(e.payload for e in initialized if e.kind==0x55b)==initialization_payload(store.load_skills())
print('PASS: equip, move, swap, unequip, duplicate replay, restart, invalid/locked skills and location/UI/key isolation.')
