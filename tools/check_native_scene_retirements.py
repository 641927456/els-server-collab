"""Verify pinned scene sources and native report gates using installed runtime assets."""
import argparse,importlib.util,sys
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('--runtime',type=Path,required=True,help='Qualified runtime root with its locked static assets')
args=parser.parse_args()
ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(args.runtime.resolve()))
import els_server.domain
for name in ('scene_retirement_sources','public_controller_rules','story_controller_retirements','scene_actor_retirements'):
    full='els_server.domain.'+name
    spec=importlib.util.spec_from_file_location(full,ROOT/'references/native-scene-retirements-20261101-v1/source/els_server/domain'/f'{name}.py')
    module=importlib.util.module_from_spec(spec);sys.modules[full]=module
    spec.loader.exec_module(module);setattr(els_server.domain,name,module)

"""All confirmed source gates, exact replay and encode-before-adopt checks."""
import copy
import json
import struct
import sys
from types import SimpleNamespace as NS
from unittest.mock import patch

from els_server.domain.dungeon_routes import DungeonRun
from els_server.domain import dungeon_flow,scene_actor_retirements as target
from els_server.protocol.protocol_codec import Event,encode_event

confirmed=json.loads((ROOT/'references/native-scene-retirements-20261101-v1/gate-cases.json').read_bytes())
cache={};results=[]


def fixture(row):
    key=(row['dungeon'],row['stage'])
    if key not in cache:
        r=DungeonRun(row['dungeon'],'00000000-0000-4000-8000-000000000001',clock=lambda:100.,internal=row['route_group']=='internal_routes')
        r._load_stage(row['stage']);cache[key]=r
    run=copy.copy(cache[key]);run.parts=copy.deepcopy(run.parts);run.part=row['part'];run.started_at=0.
    run.defeated={};run.next=None;run.ready_at=None
    if run.encounter and run.encounter['kind']=='gold_castle':run.completed_stages=set(run.encounter['wings'])
    npc=next(n for n in run.current['npcs']if(n['template'],n['source_index'])==(row['template'],row['source_index']))
    run.defeated={n['key']:b'controlled-other-completion'for n in run.current['npcs']if n is not npc}
    owner=1004
    s=NS(dungeon_run=run,phase='dungeon_active',role='game',account=NS(uid=owner,
        character=lambda:{'unit_type':1,'level':99}),dungeon_substage_synced=True,
        clear_notified=False,dungeon_failed=False,part_end_notified=False,challenge_deadline=None,
        dungeon_clock=NS(total=0.,started=0.,pause=lambda:None),summon_keys=set(),
        dungeon_participants=frozenset((owner,)),reward_run_id=run.run_id,reward_transaction=None)
    body=(struct.pack('>iBQQ6fBf',npc['key'],255,2**64-1,2**64-1,0,0,0,0,0,0,1,npc['hp'])
        +struct.pack('>IIQBQIQ',0,1,owner,0,0,0,0))
    return s,npc,Event(0x202,kind=0xad,performers=(0,),payload=body)


for row in confirmed:
    s,npc,event=fixture(row);run=s.dungeon_run
    conditions=[c for c in run.current['conditions']if c['kind']in(1,2)and npc['key_code']in c['required']
        or c['kind']==3 and npc['template']in c['required']]
    assert conditions and not any(run.condition_ready(c)for c in conditions)
    reply=dungeon_flow.handle(s,event)
    assert reply and reply[0].kind==0xae,(row,[e.kind for e in reply])
    assert all(run.condition_ready(c)for c in conditions),row
    snapshot=(copy.deepcopy(run.current),dict(run.defeated),run.next,run.ready_at,s.part_end_notified)
    assert[e.kind for e in dungeon_flow.handle(s,event)]==[0xae],row
    bad=bytearray(event.payload);struct.pack_into('>f',bad,21,1.)
    assert dungeon_flow.handle(s,Event(0x202,kind=0xad,payload=bytes(bad)))==[],row
    assert snapshot==(run.current,run.defeated,run.next,run.ready_at,s.part_end_notified)
    results.append(dict(dungeon=row['dungeon'],stage=row['stage'],part=row['part'],template=row['template'],
        accepted=True,original_condition_ready=True,replay_ack_only=True,conflict_unchanged=True))

# The new public lifecycle path encodes every response before adopting state.
s,npc,event=fixture(confirmed[0]);run=s.dungeon_run
before=(copy.deepcopy(run.current),dict(run.defeated),run.next,run.ready_at,s.part_end_notified)
with patch('els_server.protocol.protocol_codec.encode_event',side_effect=RuntimeError('controlled encoder failure')):
    try:dungeon_flow.handle(s,event)
    except RuntimeError as error:assert str(error)=='controlled encoder failure'
    else:raise AssertionError('Failed reply encoding unexpectedly committed')
assert before==(run.current,run.defeated,run.next,run.ready_at,s.part_end_notified)

output=dict(ok=True,source_gates=len(results),rows=results,encoding_failure_preserves_state=True,
    full_Application=False,natural_battle=False)

print(json.dumps(dict(ok=True,source_gates=len(results),encoding_rollback=True)))

"""Verify every finite declaration against actual emitted source instances."""
import copy,json,uuid
from els_server.domain.dungeon_routes import DungeonRun
from els_server.domain.scene_retirement_sources import RULES
from els_server.domain.scene_actor_retirements import finite_source_rule

def identity(r):return r['dungeon'],r['stage'],r['part'],json.dumps(r['source'],sort_keys=True)
remaining={identity(r):r for r in RULES};verified=[];negatives=0
for attempt in range(40):
    locations={(r['dungeon'],r['stage'])for r in remaining.values()}
    for mid,stage in sorted(locations):
        run=DungeonRun(mid,str(uuid.UUID(int=attempt+1)),clock=lambda:100.,internal=True)
        run._load_stage(stage)
        for part in run.parts:
            run.part=part
            for npc in run.current['npcs']:
                matches=[(key,r)for key,r in remaining.items()if (r['dungeon'],r['stage'],r['part'])==(mid,stage,part)
                    and all(npc.get(k)==v for k,v in r['source'].items())]
                for key,r in matches:
                    assert finite_source_rule(run,npc) is not None,key
                    for field,value in [('hp',npc['hp']+1),('dynamic',True),('source_index',-1234),('start_point',-1),('key_code',-1234)]:
                        old=npc.get(field);present=field in npc;npc[field]=value
                        assert finite_source_rule(run,npc) is None,(key,field)
                        if present:npc[field]=old
                        else:del npc[field]
                        negatives+=1
                    old=run.graph;run.graph=copy.deepcopy(old);run.graph['source_sha256']='0'*64
                    assert finite_source_rule(run,npc) is None,key
                    run.graph=old;negatives+=1
                    verified.append(key);del remaining[key]
    if not remaining:break
output=dict(ok=not remaining,rules=len(RULES),verified=len(verified),negative_checks=negatives,
    seeds=attempt+1,remaining=list(remaining),original_emitted_instances=True,natural_battle=False)

print(json.dumps(output));assert not remaining
