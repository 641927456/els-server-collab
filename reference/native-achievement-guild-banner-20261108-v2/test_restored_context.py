"""An accepted badge is replayable only for its same current actor scene."""
from qa_environment_v2 import F
from types import SimpleNamespace
import copy,hashlib,json,struct,time
from els_server.domain import guild_banner_flow as banner
from els_server.protocol.protocol_codec import encode_event

room={};s=SimpleNamespace(phase='town_ready',active_map=20001,shop_session_id='owned-scene-a',
    dungeon_run=None,account=SimpleNamespace(uid=1001))
s.guild_banner=dict(active=True,guild=1,appearance=[],scope=banner._scope(s),room=room)
original=copy.copy(s.guild_banner)
events=banner.restored(s,room)
assert len(events)==1 and events[0].kind==0x7e2
assert events[0].payload==struct.pack('>Q?I',1001,True,0)
encode_event(events[0])
assert banner.restored(s,{})==[]
for field,value in(('phase','guild_agit_ready'),('active_map',20002),('shop_session_id','owned-scene-b')):
    actor=copy.copy(s);setattr(actor,field,value)
    assert banner.restored(actor,room)==[],field
for current in(None,dict(original,active=False)):
    actor=copy.copy(s);actor.guild_banner=current
    assert banner.restored(actor,room)==[]
assert s.guild_banner==original
report=dict(ok=True,current_scene_only=True,equal_but_distinct_room_rejected=True,
    old_phase_map_session_rejected=True,withdrawn_and_absent_not_replayed=True,
    state_not_mutated=True,production_database_access=False,native_Game=False,
    helper_sha256=hashlib.sha256(__import__('pathlib').Path(banner.__file__).read_bytes()).hexdigest())
(F/('restore-context-'+str(time.time_ns())+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps(report))
