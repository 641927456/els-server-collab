"""Two loaded members use the existing shared scene-retirement dispatcher."""
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import json,struct,sys,uuid

from runtime_support import ROOT, server_root
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(server_root()))
import els_server.domain
els_server.domain.__path__.insert(0,str(ROOT/'source/els_server/domain'))
from els_server.domain.dungeon_routes import DungeonRun
from els_server.domain.dungeon_clock import DungeonClock
from els_server.domain.friends_dungeon import FriendsDungeons,Room
from els_server.domain.friends_world import Mailbox
from els_server.domain.friends_spawns import capture_static_origin
from els_server.protocol.protocol_codec import Event
from fixture_session import session

class Member(NS):
    __hash__=object.__hash__

seed='00000000-0000-4000-8000-000000000001'
world=NS(party_of={},members={})
dispatcher=FriendsDungeons(world);world.dungeons=dispatcher
app=NS(playing={},accounts={},world=world,registry=NS(enabled=lambda _:True))
members=[]
for i in range(2):
    run=DungeonRun(34760,seed,internal=True);run._load_stage(0);run.part=1;run.loaded()
    run.defeated={n['key']:b'accepted original combat fixture' for n in run.current['npcs'] if n['active'] and n['key']!=28}
    m=Member(**vars(session(run,part_end_notified=False)))
    m.dungeon_clock=DungeonClock();m.dungeon_clock.resume()
    m.application=app;m.gate_stage_loading=False;m.gate_stage=0;m.dungeon_failed=False
    m.client_build='dx11_260923';m.population_test=True;m.dungeon_return_pending=False
    m.summon_deaths={};m.summon_requests={};m.summon_next_key=80
    a=m.account;a.uid=1001+i;a.account_id=71+i;a.store.uid=a.uid;a.root.character_accounts={a.uid:a}
    m.identity={'id':a.account_id};app.playing[a.account_id]=m;app.accounts[a.account_id]=a.root
    m.dungeon_participants=frozenset((1001,1002));m.shop_session_id='isolated-'+str(i)
    m.coop_error=False;m.social_overflow=False;m.mailbox=Mailbox()
    m.reward_run_id=str(uuid.uuid5(uuid.UUID(seed),'reward:'+str(a.uid)))
    members.append(m)
members=tuple(members);leader,peer=members
party=dict(members=members,leader=leader)
room=Room(party,members,leader,34760,seed,phase='active');party['run']=room
for m in members:world.party_of[m]=party;dispatcher.rooms[m]=room
capture_static_origin(room)
npc=next(n for n in leader.dungeon_run.current['npcs']if n['key']==28)
assert npc['hp']==332821472
payload=struct.pack('>iBQQ6fBf',28,255,2**64-1,2**64-1,0,0,0,0,0,0,1,npc['hp'])
payload+=struct.pack('>IIQBQBQIQ',0,2,1001,0,1002,0,0,0,0)
event=Event(0x202,performers=(0,),kind=0xad,payload=payload)
with patch('els_server.domain.pve_economy_flow.prepared_death',side_effect=AssertionError('unexpected solo economy')):
    reply=dispatcher.death(room,leader,event,7001)
assert [e.kind for e in reply]==[0xae,0xaf,0xb7],[e.kind for e in reply]
assert [e.kind for e in peer.mailbox.drain()]==[0xaf,0xb7]
assert all(m.dungeon_run.defeated[28]==payload and m.dungeon_run.part==1 for m in members)
assert [e.kind for e in dispatcher.death(room,leader,event,7001)]==[0xae]
assert not peer.mailbox.drain()
assert all(not m.world_drops for m in members)
result=dict(ok=True,members=2,npc_hp=332821472,shared_retirement=True,source_gate_opened=True,
            replay_no_duplicate_notice=True,natural_multiplayer=False,production_database_access=False)
print(json.dumps(result))
