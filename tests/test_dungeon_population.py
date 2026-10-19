"""Original active roster, two transitions, premature/duplicate death rejection."""
import json,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
from dungeon_population import population,substage
from dungeon_route import route,progress
from local_session import LocalSession
from protocol_codec import Event
from dungeon_clear import prototype_clear_notice
try:LocalSession(reward_probe=True)
except ValueError:pass
else:raise AssertionError('Unisolated reward probe')
default=prototype_clear_notice().payload;marked=prototype_clear_notice(True).payload
assert default!=marked and len(default)==len(marked)==516 and default[:31]==marked[:31]
assert [[n['template'] for n in population(s)['npcs']] for s in range(3)]==[
 [618,618,618,201,201,201,625,626],[632,618,618,618,201,201,201,618,201,625,626],[5,20]]
assert [sum(n['active'] for n in population(s)['npcs']) for s in range(3)]==[6,8,1]
assert all(substage(s).payload[:8]==struct.pack('>ii',s,0) for s in range(3))
try:LocalSession(population_test=True)
except ValueError:pass
else:raise AssertionError('Unisolated population profile')
s=LocalSession(enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,gate_test=True,population_test=True)
s.role='game';s.phase='dungeon_active';s.dungeon_substage_synced=True
body=bytes.fromhex(json.loads((ROOT/'analysis/client-6c6b5180/20261013-160720/death-event-header.json').read_text(encoding='utf8'))[0]['payload'])
def death(n):
 b=bytearray(body);struct.pack_into('>i',b,0,n['key']);struct.pack_into('>f',b,struct.calcsize('>iBQQ6fB'),n['hp'])
 # The source packet's native maximum HP field offset is derived from its schema.
 from dungeon_lifecycle import death_report
 assert death_report(b)['hp_bits']==struct.unpack('>I',struct.pack('>f',n['hp']))[0]
 return Event(0x202,performers=(0,),kind=0xad,payload=bytes(b))
before=(s.account.get_location(),s.account.get_skills())
for stage in range(3):
 p=population(stage);clear=p['npcs'][p['clear_key']]
 if stage<2:assert s.handle(death(clear))==[]
 for n in p['npcs']:
  if n['active'] and n!=clear:
   e=death(n);assert [r.kind for r in s.handle(e)]==[0xae,0xaf]
   assert [r.kind for r in s.handle(e)]==[0xae]
   assert not s.part_end_notified
 assert [r.kind for r in s.handle(death(clear))]==[0xae,0xaf,0xba]
 assert [r.kind for r in s.handle(Event(0x202,kind=0xbb,payload=b'\0'))]==([0xbc,0xb2] if stage<2 else [0xbc])
 if stage<2:
  assert s.gate_stage==stage+1 and not s.dungeon_substage_synced
  assert [r.kind for r in s.handle(Event(0x202,kind=0xbb,payload=b'\0'))]==[0xbc]
  assert s.handle(death(clear))==[]
  loaded=Event(0x202,kind=0xb3,payload=bytes.fromhex('000000000040b66666'))
  assert [r.kind for r in s.handle(loaded)]==[0xb4,0xb5,0xb6,0xb7,0xbd]
assert before==(s.account.get_location(),s.account.get_skills())
t=LocalSession(enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,gate_test=True,population_test=True,clear_test=True)
t.role='game';t.phase='dungeon_active';t.dungeon_substage_synced=True;t.gate_stage=2
bb=Event(0x202,kind=0xbb,payload=b'\0')
assert t.handle(bb)==[] and not t.clear_notified
assert [r.kind for r in t.handle(death(population(2)['npcs'][0]))]==[0xae,0xaf,0xba]
assert [r.kind for r in t.handle(bb)]==[0xbc,0xc1] and t.clear_notified
assert [r.kind for r in t.handle(bb)]==[0xbc]
assert before==(t.account.get_location(),t.account.get_skills())
wrong=Event(0x202,kind=0x225,payload=struct.pack('>iB',20002,0))
assert t.handle(wrong)==[] and t.phase=='dungeon_active'
town=Event(0x202,kind=0x225,payload=struct.pack('>iB',t.account.get_location()['map'],0))
assert [r.kind for r in t.handle(town)]==[0x226] and t.phase=='square_accepted'
r=route(1);poses=[[2221.5417,698,-835.3244],[2304,698,-350.5222],[2290.31,698,148.413],[100.131,698,2465.53]]
values=[progress(r,p) for p in poses]
assert values==sorted(values) and values[-1]-values[0]>4300
assert abs(progress(r,poses[1])-progress(r,[2304,938,-350.5222]))<.01
print('PASS: original 8/11/2 roster, active counts6/8/1, gated transitions, duplicate/load guards, local balance isolation, curved-route native poses.')
