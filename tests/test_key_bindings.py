"""Key save/reconnect, corrupt input and isolation from position/HUD saves."""
import sys,struct,tempfile
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from key_bindings import DEFAULT_BINDINGS,validate_bindings
from local_state import LocalState
from local_session import LocalAccount,LocalSession
from local_messages import key_bindings_initialization,i32
from protocol_codec import Event
bindings=struct.pack('>Ihhhh',2,0,43,1,44)+bytes(8)
assert key_bindings_initialization().payload==bytes(16)
with tempfile.TemporaryDirectory(prefix='keys-test-',dir=BASE/'analysis') as folder:
    path=Path(folder)/'save.sqlite3';store=LocalState(path)
    store.save(20001,26,49,(-314.,372.,-483.));location=store.load();layout=store.load_layout()
    s=LocalSession(LocalAccount(store),True);s.phase='characters_ready';s.role='game'
    ack=s.handle(Event(0x202,kind=0x397,payload=bindings))[0]
    assert ack.kind==0x398 and ack.payload==i32(0)
    restarted=LocalAccount(LocalState(path));assert restarted.get_bindings()==bindings
    assert key_bindings_initialization(restarted.get_bindings()).payload==i32(0)+bindings
    for bad in [b'',bindings[:-1],bindings+b'\0',b'\xff'*4+bindings[4:],struct.pack('>Ihhhh',2,0,43,0,44)+bytes(8),struct.pack('>Ihh',1,-1,43)+bytes(8),struct.pack('>Ihh',1,0,165)+bytes(8)]:
        assert s.handle(Event(0x202,kind=0x397,payload=bad))[0].payload==i32(-1)
        assert store.load_bindings()==bindings and store.load()==location and store.load_layout()==layout
    s.handle(Event(0x202,kind=0x397,payload=bindings))
    with store.connect() as db:assert db.execute('SELECT revision FROM key_bindings').fetchone()[0]==1
    new=LocalSession(enter_town=True);assert new.handle(Event(0x202,kind=0x397,payload=bindings))==[]
print('PASS: durable key reconnect, duplicate saves, malformed records and position/HUD isolation.')
import json
native=json.loads((BASE/'analysis/runs/20261012-200954-158048/local-bootstrap.json').read_text(encoding='utf8'))
from protocol_codec import decode_event
recorded=[decode_event(bytes.fromhex(e['plaintext_hex'])).payload for c in native['connections'] for e in c.get('decoded_events',[]) if e['kind']==0x397]
assert recorded and len(recorded[0])==352 and validate_bindings(recorded[0])==recorded[0]
print('PASS: original native 85-entry keyboard save, including reserved -1 sentinels.')
