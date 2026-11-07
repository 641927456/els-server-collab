"""Actual authenticated Application/TLS with owned explicit scene fixtures."""
from pathlib import Path
from dataclasses import replace
from contextlib import closing
import ast,asyncio,copy,importlib.util,json,os,sqlite3,struct,sys,traceback
H=Path(__file__).resolve().parent;W=H.parent;R=Path('G:/els');C=H/'candidate'
sys.dont_write_bytecode=True;os.environ['ELS_CRASH_TEST_RUNTIME']=str(C);sys.argv=[__file__]
spec=importlib.util.spec_from_file_location('owned_v9_fixture',W/'reproduce_tutorial_late_death.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
from els_server.domain import scene_actor_retirements as flow,friends_spawns
from els_server.domain.dungeon_routes import SOURCE_NPC_GROUP_WEIGHTS
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import wstring
from els_server.game_data import client_data
from els_server.storage.seal_quests import ensure
tree=ast.parse((W/'repair-v8/test_ship_repairs.py').read_bytes())
names=('new_character','economy','death','observe','barrier','assert_no_errors')
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))and n.name in names],type_ignores=[]),'unchanged_owned_helpers','exec'),globals())

def scene(s,stage,part,group=0):
 run=s.dungeon_run;draw=run.draw;weights=SOURCE_NPC_GROUP_WEIGHTS.get((run.graph['source_sha256'],stage,part))
 run.draw=lambda label,total:sum(weights[:group])if weights and label==f'group:{stage}:{part}'else draw(label,total)
 try:run._load_stage(stage)
 finally:del run.draw
 run.part=part;run.next=None;run.ready_at=None;run.loaded()
 s.gate_stage=stage;s.dungeon_substage_synced=True;s.gate_stage_loading=False;s.part_end_notified=False;s.defeated_npcs=run.defeated
 return run

async def send_death(peer,npc,owners,events):
 body=death(npc,owners);mark=len(events)
 await peer.send(0xad,body);assert(await peer.until(0xae)).payload==bytes(4)
 af=await peer.until(0xaf)
 assert struct.unpack('>iiBQII?iiI',af.payload)==(npc['key'],0,0,2**64-1,0,0,False,0,0,0)
 await barrier(peer)
 assert sum(isinstance(e,Event)and e.kind==0xaf for e in events[mark:])==1
 return body

async def refuse(peer,body,events):
 mark=len(events);await peer.send(0xad,body);await barrier(peer)
 assert not any(isinstance(e,Event)and e.kind in(0xae,0xaf)for e in events[mark:])

async def solo(dungeon):
 f=r.f.FriendsTests();await f.asyncSetUp()
 try:
  uid=new_character(f,f.alice);peer=await f.peer(f.alice);await peer.roster();await r.admit(peer,uid,dungeon)
  s=f.app.playing[f.alice['id']];events=observe(peer);before=economy(f.config.state_file,uid);accepted=0
  for group in range(3 if dungeon==33242 else 1):
   stage,part=(3,0)if dungeon==33242 else(1,1)
   run=await f.app.call(scene,s,stage,part,group)
   targets=[n for n in run.current['npcs']if n['template']==2316]if dungeon==33881 else[n for n in run.current['npcs']if n['template']not in(1391,1395)]
   assert targets
   if dungeon==33242:
    trigger=next(n for n in run.current['npcs']if n['template']==1395)
    assert flow.source_rule(run,targets[0])is None
    await refuse(peer,death(targets[0],[uid]),events)
    assert not run.defeated
    # Reject an unacknowledged inactive controller, not just an active flag.
    trigger['active']=False
    assert flow.source_rule(run,targets[0])is None
    trigger['active']=True
    await send_death(peer,trigger,[uid],events)
    assert run.next is not None
    excluded=next(n for n in run.current['npcs']if n['template']==1391)
    await refuse(peer,death(excluded,[uid]),events)
   npc=targets[0];body=death(npc,[uid]);gate=(run.next,run.ready_at,s.part_end_notified)
   # Full actor/source and HP must remain identical to the emitted roster.
   original=npc['team'];npc['team']=7
   await refuse(peer,body,events);npc['team']=original
   original=npc['hp'];npc['hp']*=2
   await refuse(peer,body,events);npc['hp']=original
   await refuse(peer,death(npc,[uid+1]),events)
   s.dungeon_substage_synced=False
   await refuse(peer,body,events);s.dungeon_substage_synced=True
   if dungeon==33242:
    original=trigger['source_context'];trigger['source_context']=(*original[:5],999,original[6])
    await refuse(peer,body,events);trigger['source_context']=original
   for npc in targets:
    assert flow.source_rule(run,npc)is not None
    body=await send_death(peer,npc,[uid],events);accepted+=1
    mark=len(events);await peer.send(0xad,body);assert(await peer.until(0xae)).payload==bytes(4);await barrier(peer)
    assert not any(isinstance(e,Event)and e.kind==0xaf for e in events[mark:])
    assert npc['active']is False and run.defeated[npc['key']]==body
   if dungeon==33881:
    assert(run.next,run.ready_at,s.part_end_notified)==gate
   assert economy(f.config.state_file,uid)==before
  assert_no_errors(f)
  return dict(ok=True,dungeon=dungeon,groups=3 if dungeon==33242 else 1,retired=accepted,
      valid_AE_empty_AF=True,retry_ACK_only=True,forged_source_HP_readiness_unsynced_refused=True,
      causal_controller_required=dungeon==33242,economy_unchanged=True)
 finally:await f.asyncTearDown()

async def shared(dungeon):
 f=r.f.FriendsTests();await f.asyncSetUp()
 try:
  uids=[new_character(f,a)for a in(f.alice,f.bob)];a,b=uids
  f.config=replace(f.config,friends_coop_enabled=True);f.app.config=f.config;f.server.config=f.config
  alice,bob=await asyncio.gather(f.peer(f.alice),f.peer(f.bob));await asyncio.gather(alice.roster(),bob.roster())
  await alice.enter_town(a);await bob.enter_town(b)
  invitation=struct.pack('>Q',b)+wstring('Ship'+str(f.bob['id']))+struct.pack('>iBi',0,1,dungeon)+bytes(6)+wstring('')+bytes(15)
  await alice.send(0x136,invitation);await alice.until(0x137);await bob.until(0x138)
  await bob.send(0x139,struct.pack('>QQBiBQ',a,b,1,0,0,0));await bob.until(0x13a);await asyncio.gather(alice.until(0x13b),bob.until(0x13b))
  await f.coop_start(alice,bob,dungeon);await f.coop_load(alice,bob)
  sessions=list(f.app.playing.values());s=f.app.playing[f.alice['id']];room=f.app.world.dungeons.room(s)
  def setup():
   for member in sessions:scene(member,*( (3,0)if dungeon==33242 else(1,1)))
   room.phase='active';friends_spawns.capture_static_origin(room)
  await f.app.call(setup);events={p:observe(p)for p in(alice,bob)};before={uid:economy(f.config.state_file,uid)for uid in uids}
  if dungeon==33242:
   trigger=next(n for n in s.dungeon_run.current['npcs']if n['template']==1395)
   await alice.send(0xad,death(trigger,uids));assert(await alice.until(0xae)).payload==bytes(4)
   await asyncio.gather(alice.until(0xaf),bob.until(0xaf))
  npc=next(n for n in s.dungeon_run.current['npcs']if n['template']==(2316 if dungeon==33881 else 1392))
  body=death(npc,uids)
  await bob.send(0xad,body);await barrier(bob)
  assert all(npc['key']not in member.dungeon_run.defeated for member in sessions)
  await refuse(alice,death(npc,[a]),events[alice])
  await alice.send(0xad,body);assert(await alice.until(0xae)).payload==bytes(4)
  await asyncio.gather(alice.until(0xaf),bob.until(0xaf));await barrier(alice);await barrier(bob)
  marks={p:len(events[p])for p in(alice,bob)}
  await alice.send(0xad,body);assert(await alice.until(0xae)).payload==bytes(4);await barrier(alice);await barrier(bob)
  assert all(not any(isinstance(e,Event)and e.kind==0xaf for e in events[p][marks[p]:])for p in(alice,bob))
  assert all(member.dungeon_run.defeated[npc['key']]==body for member in sessions)
  assert all(economy(f.config.state_file,uid)==before[uid]for uid in uids);assert_no_errors(f)
  return dict(ok=True,dungeon=dungeon,participants=2,guest_and_missing_readiness_refused=True,first_empty_AF_broadcast=True,retry_ACK_only=True,economy_unchanged=True)
 finally:await f.asyncTearDown()

async def main():
 result=dict(ok=False,actual_Application_TLS=True,explicit_owned_scene_fixtures=True,natural_GUI=False,production_modified=False,solo=[],shared=[])
 for dungeon in(33881,33242):
  result['solo'].append(await solo(dungeon))
  (H/'retirements-TLS.partial.json').write_bytes((json.dumps(result,indent=2)+'\n').encode())
 for dungeon in(33881,33242):
  result['shared'].append(await shared(dungeon))
  (H/'retirements-TLS.partial.json').write_bytes((json.dumps(result,indent=2)+'\n').encode())
 result['ok']=True
 return result

if __name__=='__main__':
 result=dict(ok=False)
 try:result=asyncio.run(main())
 except BaseException:result.update(error=traceback.format_exc());raise
 finally:
  (H/'retirements-TLS.json').write_bytes((json.dumps(result,indent=2)+'\n').encode());print(json.dumps(result))
