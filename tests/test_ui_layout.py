"""Native HUD round trip, reconnect, malformed input and save isolation."""
import sys,tempfile,struct
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from ui_layout import DEFAULT_LAYOUT,encode_layout,decode_layout
from local_state import LocalState
from local_session import LocalAccount,LocalSession
from protocol_codec import Event
wire=encode_layout(DEFAULT_LAYOUT)
assert len(wire)==33 and decode_layout(wire)==DEFAULT_LAYOUT
with tempfile.TemporaryDirectory(prefix='hud-test-',dir=BASE/'analysis') as folder:
    path=Path(folder)/'save.sqlite3';store=LocalState(path)
    store.save(20001,2,50,(1.,2.,3.));location=store.load()
    account=LocalAccount(store);s=LocalSession(account,True);s.role='game';s.phase='town_ready'
    changed=(410,640,215,680,12,701,90,20,25,1,16)
    ack=s.handle(Event(0x202,kind=0x6eb,payload=encode_layout(changed)))
    assert ack[0].kind==0x6ec and ack[0].payload==struct.pack('>i',0)
    reopened=LocalState(path);assert reopened.load_layout()==changed and reopened.load()==location
    session=LocalSession(LocalAccount(reopened),True);session.phase='player_initialized';session.role='game'
    loaded=session.handle(Event(0x202,kind=0x6e9))[0]
    assert loaded.kind==0x6ea and decode_layout(loaded.payload)==changed
    for invalid in [b'',wire[:-1],wire+b'\0',wire[:24]+b'\0\0'+wire[26:],wire[:30]+b'\2'+wire[31:]]:
        ack=s.handle(Event(0x202,kind=0x6eb,payload=invalid))[0]
        assert ack.payload==struct.pack('>i',-1)
        assert reopened.load_layout()==changed and reopened.load()==location
    s.handle(Event(0x202,kind=0x6eb,payload=encode_layout(changed)))
    with store.connect() as db:assert db.execute('SELECT revision FROM ui_layout').fetchone()[0]==1
print('PASS: complete HUD payload, durable reconnect, duplicate and malformed save controls; location unchanged.')
