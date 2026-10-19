"""Replay the authenticated native request, ordering, malformed/duplicate controls."""
import json,sys,struct
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from dungeon_lifecycle import death_report
from local_session import LocalSession
from protocol_codec import Event
capture=json.loads((BASE/'analysis/client-6c6b5180/20261013-160720/death-event-header.json').read_text())[0]
payload=bytes.fromhex(capture['payload']);data=death_report(payload)
assert data['index']==0 and data['killer']==1001 and data['contribution'].keys()=={1001}
request=Event(0x202,performers=tuple(capture['performers']),kind=0xad,payload=payload)
def session():
 s=LocalSession(enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True)
 s.role='game';s.phase='dungeon_active';s.dungeon_substage_synced=True
 return s
s=session();before=(s.account.get_location(),s.account.get_skills())
assert s.handle(Event(0x202,kind=0xbb,payload=b'\0'))==[]
answer=s.handle(request);assert [e.kind for e in answer]==[0xae,0xaf,0xba]
assert answer[1].payload==struct.pack('>iiBQII?iiI',0,0,0,1001,0,0,False,0,0,0)
assert [e.kind for e in s.handle(request)]==[0xae]
assert len(s.defeated_npcs)==1
assert [e.kind for e in s.handle(Event(0x202,kind=0xbb,payload=b'\0'))]==[0xbc]
assert [e.kind for e in s.handle(Event(0x202,kind=0xbb,payload=b'\0'))]==[0xbc]
assert (s.account.get_location(),s.account.get_skills())==before
for e in [Event(0x402,performers=(0,),kind=0xad,payload=payload),Event(0x202,kind=0xad,payload=payload),Event(0x202,performers=(1,),kind=0xad,payload=payload),Event(0x202,performers=(0,),kind=0xad,payload=payload+b'\0'),Event(0x202,performers=(0,),kind=0xad,payload=payload[:-1])]:
 t=session();assert t.handle(e)==[] and t.defeated_npcs=={}
for offset,value in [(0,struct.pack('>i',1)),(5,struct.pack('>Q',999)),(21,struct.pack('>f',float('nan'))),(50,struct.pack('>I',81))]:
 corrupt=payload[:offset]+value+payload[offset+len(value):]
 t=session();assert t.handle(Event(0x202,performers=(0,),kind=0xad,payload=corrupt))==[] and not t.defeated_npcs
for phase in ('new','town_ready','dungeon_loading','map_loading'):
 t=session();t.phase=phase;assert t.handle(request)==[]
assert LocalSession(enter_town=True,enter_dungeon=True,client_build='dx11_260923').handle(request)==[]
print('PASS: real death-report schema, participant/phase bounds, corrupt maps/scalars, once-only AF/BA, no repeated BD start and save isolation; experimental only.')
