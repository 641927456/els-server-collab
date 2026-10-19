"""Real movement parsing, durable restart, rejected input and atomic location updates."""
import json,sys,tempfile,struct
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from local_state import LocalState,movement_location
from local_session import LocalSession,LocalAccount,SessionOrderError
from local_messages import i32,player_initialization
from protocol_codec import Event,decode_event
capture=json.loads((BASE/'analysis/runs/20261012-190505-111598/local-bootstrap.json').read_text())
payloads=[decode_event(bytes.fromhex(e['plaintext_hex'])).payload for c in capture['connections'] for e in c.get('decoded_events',[]) if e['kind']==0x22b]
assert len(payloads)>=10
assert movement_location(payloads[-1])[:2]==(11,85)
with tempfile.TemporaryDirectory(prefix='state-test-',dir=BASE/'analysis') as folder:
    path=Path(folder).resolve()/'local.sqlite3';assert path.is_relative_to((BASE/'analysis').resolve())
    store=LocalState(path);account=LocalAccount(store);s=LocalSession(account,enter_town=True)
    for k in [0x1a,0x1e,0x35,0x1ef,0x39,0x485]:s.handle(Event(0x202,kind=k))
    s.handle(Event(0x202,kind=0x28,payload=struct.pack('>Q',1001)))
    for k in [0x6e9,0x5bf,0x32]:s.handle(Event(0x202,kind=k))
    s.handle(Event(0x202,kind=0x225,payload=i32(20000)+b'\x00'))
    assert store.load()['revision']==0,'Map request saved before scene arrival'
    s.handle(Event(0x202,kind=0x227,payload=struct.pack('>fffBH',488,151,-802,0,0)))
    for p in payloads:s.handle(Event(0x202,kind=0x22b,payload=p))
    saved=LocalState(path).load();assert (saved['map'],saved['board'],saved['progress'])==(20000,11,85)
    s.handle(Event(0x202,kind=0x22b,payload=payloads[-1]));assert store.load()['revision']==saved['revision']
    for p in [payloads[-1][:-1],payloads[-1][:12]+b'\xff'*4+payloads[-1][16:],struct.pack('>fff',float('nan'),0,0)+payloads[-1][12:]]:
        try:s.handle(Event(0x202,kind=0x22b,payload=p))
        except SessionOrderError:pass
        else:raise AssertionError('Malformed movement accepted')
        assert store.load()==saved
    s.handle(Event(0x202,kind=0x225,payload=i32(20001)+b'\x00'))
    assert store.load()==saved,'Portal persisted before the destination scene loaded'
    s.handle(Event(0x202,kind=0x227,payload=struct.pack('>fffBH',1,2,3,0,50)))
    restored=LocalAccount(LocalState(path)).get_location();assert (restored['map'],restored['progress'])==(20001,50)
    packet=player_initialization(restored).payload
    assert i32(20001)+b'\x00\x00\x32\x00' in packet
    response=s.handle(Event(0x202,kind=0x490))
    assert s.phase=='channels_ready' and [e.kind for e in response]==[0x327,0x491]
    s.handle(Event(0x202,kind=0x233));assert s.phase=='closing'
    assert store.load()==restored
print('PASS: recorded movement, location restart, portal arrival commit, duplicate and malformed controls.')
