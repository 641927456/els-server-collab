"""Gate profile stays isolated and does not clear before gate evidence exists."""
import json,struct,sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from dungeon_npcs import gate_test_maps,updated_spawn_map,MODE0_FIELDS
from dungeon_messages import initial_substage
from local_session import LocalSession
from protocol_codec import Event
spawns,init=gate_test_maps()
assert struct.unpack_from('>IiII',spawns)==(1,0,0,3)
assert struct.unpack_from('>I',init)[0]==3
# This profile enables active-count participation for its training NPC.
before=updated_spawn_map(0)[16:];after=spawns[16:132]
offset=0
for field,n,_,_ in MODE0_FIELDS:
 if field==0x4e:break
 offset+=n
assert before[:offset]==after[:offset] and before[offset+1:]==after[offset+1:] and (before[offset],after[offset])==(0,1)
assert initial_substage('dx11_260923',0).payload!=initial_substage('dx11_260923',0,gate_test=True).payload
for kw in [{},{'npc_slot_test':True},{'npc_slot_test':True,'enter_dungeon':True}]:
 try:LocalSession(gate_test=True,**kw)
 except ValueError:pass
 else:raise AssertionError('Invalid gate profile accepted')
s=LocalSession(enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,gate_test=True)
s.role='game';s.phase='dungeon_active';s.dungeon_substage_synced=True
payload=bytes.fromhex(json.loads((BASE/'analysis/client-6c6b5180/20261013-160720/death-event-header.json').read_text())[0]['payload'])
before=(s.account.get_location(),s.account.get_skills())
assert [e.kind for e in s.handle(Event(0x202,performers=(0,),kind=0xad,payload=payload))]==[0xae,0xaf]
assert not s.part_end_notified and s.handle(Event(0x202,kind=0xbb,payload=b'\0'))==[]
assert before==(s.account.get_location(),s.account.get_skills())
gate_capture=json.loads((BASE/'analysis/client-6c6b5180/20261013-170652/gate-death-event-header.json').read_text())[-1]
t=LocalSession(enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,gate_test=True)
t.role='game';t.phase='dungeon_active';t.dungeon_substage_synced=True
assert t.handle(Event(0x202,performers=tuple(gate_capture['performers']),kind=0xad,payload=bytes.fromhex(gate_capture['payload'])))==[] and not t.defeated_npcs
gate_payload=struct.pack('>i',1)+bytes.fromhex(gate_capture['payload'])[4:]
gate_request=Event(0x202,performers=(0,),kind=0xad,payload=gate_payload)
assert t.handle(gate_request)==[] and not t.defeated_npcs  # before training death
answer=s.handle(gate_request)
assert [e.kind for e in answer]==[0xae,0xaf,0xba]
assert struct.unpack_from('>i',answer[1].payload)[0]==1
assert [e.kind for e in s.handle(gate_request)]==[0xae]
assert s.part_end_notified and [e.kind for e in s.handle(Event(0x202,kind=0xbb,payload=b'\0'))]==[0xbc,0xb2]
assert s.gate_stage==1 and s.gate_stage_loading and not s.dungeon_substage_synced and not s.defeated_npcs
assert [e.kind for e in s.handle(Event(0x202,kind=0xbb,payload=b'\0'))]==[0xbc]  # no repeated B2
assert s.handle(gate_request)==[]  # old-stage death during loading
loaded=Event(0x202,kind=0xb3,payload=bytes.fromhex('000000000040b66666'))
assert [e.kind for e in s.handle(loaded)]==[0xb4,0xb5,0xb6,0xb7,0xbd]
assert s.dungeon_substage_synced and not s.gate_stage_loading
assert [e.kind for e in s.handle(loaded)]==[0xb4,0xb5]  # no repeated new-stage start
assert before==(s.account.get_location(),s.account.get_skills())
print('PASS: isolated gate profile guards, preserved training spawn, three independent native template records and no clear/reward/save mutation from training death.')
