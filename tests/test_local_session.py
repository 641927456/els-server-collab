"""Validate phases against actual requests, then try illegal order controls."""
import json,sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
from local_session import LocalSession,LocalAccount,SessionOrderError
from protocol_codec import Event,decode_event
from els_server.protocol.local_messages import channel_list,server_summary
import struct

# Native new-character auto-selection reads the first eligibility map. It
# cannot reconnect with the previously empty map, even when the UI list exists.
channel_payload=channel_list().payload
rules_start=len(server_summary().payload)-4
rule_count=struct.unpack_from('>I',channel_payload,rules_start)[0]
assert rule_count>0
rules=[struct.unpack_from('>iBiiii',channel_payload,rules_start+4+21*n) for n in range(rule_count)]
assert any(key==0 and minimum<=1<=maximum for key,flag,minimum,maximum,_,__ in rules)
assert rules_start+4+21*rule_count+4==len(channel_payload)
capture=json.loads((BASE/'analysis/runs/20261012-163220-994976/local-bootstrap.json').read_text())
for row in capture['connections']:
    session=LocalSession()
    for stored in row['decoded_events']:session.handle(decode_event(bytes.fromhex(stored['plaintext_hex'])))
    if session.role=='game':
        assert session.phase=='characters_ready'
        answer=session.handle(Event(0x202,kind=0x490))
        assert session.phase=='channels_ready' and answer[0].kind==0x491
        assert session.handle(Event(0x202,kind=0x490))==answer
for kind in [0x1e,0x35,0x485,0x490]:
    try:LocalSession().handle(Event(0x202,kind=kind))
    except SessionOrderError:pass
    else:raise AssertionError(f'{kind:x} accepted without prerequisites')
try:LocalSession().handle(Event(0x402,kind=0x1a))
except SessionOrderError:pass
else:raise AssertionError('Game login accepted from frontend event type')
print('PASS: recorded frontend/game phases, duplicate channel request and invalid order controls.')
account=LocalAccount();account.accept_terms();reconnect=LocalSession(account)
for kind in [0x1a,0x1e,0x35,0x1ef,0x485]:reconnect.handle(Event(0x202,kind=kind))
assert reconnect.phase=='characters_ready'
uncached=LocalSession()
for kind in [0x1a,0x1e,0x35,0x1ef]:uncached.handle(Event(0x202,kind=kind))
try:uncached.handle(Event(0x202,kind=0x485))
except SessionOrderError:pass
else:raise AssertionError('Skipped terms accepted without cached account state')

def town_session():
    s=LocalSession(account,enter_town=True)
    for kind in [0x1a,0x1e,0x35,0x1ef,0x485]:s.handle(Event(0x202,kind=kind))
    return s

import struct
from local_messages import LOCAL_TOWN_MAP,i32
town=town_session()
answer=town.handle(Event(0x202,kind=0x28,payload=struct.pack('>Q',1001)))
assert [e.kind for e in answer]==[0x2a,0x55b,0x2b,0x2c,0x2d,0x2e,0x30,0x2f,0x31,0x29]
for kind,phase in [(0x6e9,'skill_ui_ready'),(0x5bf,'initialization_confirmed'),(0x32,'map_loading')]:
    town.handle(Event(0x202,kind=kind));assert town.phase==phase
for payload in [b'',struct.pack('>i',30000)+b'\x01']:
    try:town.handle(Event(0x202,kind=0x225,payload=payload))
    except SessionOrderError:pass
    else:raise AssertionError('Malformed town entry accepted')
denied=town.handle(Event(0x202,kind=0x225,payload=i32(30000)+b'\x00'))
assert denied[0].payload[:4]==i32(-1) and town.phase=='map_loading'
answer=town.handle(Event(0x202,kind=0x225,payload=i32(LOCAL_TOWN_MAP)+b'\x00'))
assert town.phase=='square_accepted' and answer[0].payload==i32(0)+i32(LOCAL_TOWN_MAP)+i32(0)*3
for kind,payload in [(0x28,struct.pack('>Q',1002)),(0x6e9,b''),(0x32,b'')]:
    try:town_session().handle(Event(0x202,kind=kind,payload=payload))
    except SessionOrderError:pass
    else:raise AssertionError('Unknown character or premature town phase accepted')
print('PASS: town prerequisites, ordered skill initialization, UID and map controls.')
