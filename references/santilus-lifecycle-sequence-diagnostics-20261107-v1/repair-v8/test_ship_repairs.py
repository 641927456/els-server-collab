"""Owned authenticated TLS; explicit scene fixtures, never a player database."""
from pathlib import Path
from contextlib import closing
from dataclasses import replace
import asyncio,copy,hashlib,importlib.util,json,os,sqlite3,struct,sys,traceback
H=Path(__file__).resolve().parent;W=H.parent;R=Path('G:/els');C=H/'candidate'
SHARED_ONLY='--shared-only'in sys.argv
sys.dont_write_bytecode=True;os.environ['ELS_CRASH_TEST_RUNTIME']=str(C);sys.argv=[__file__]
spec=importlib.util.spec_from_file_location('owned_ship_repair_fixture',W/'reproduce_tutorial_late_death.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
from els_server.domain import summons,dungeon_spawns,dungeon_diagnostics,scene_actor_retirements as retire,friends_spawns
from els_server.domain.dungeon_npcs import resource_dto,encode_npc
from els_server.domain.dungeon_routes import route_catalog,SOURCE_NPC_GROUP_WEIGHTS
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import wstring
from els_server.game_data import client_data
from els_server.storage.seal_quests import ensure
CONTROLLERS=(1394,1455,1456,1457)
POSITIONS=[[158188,635,-61369],[157998,329,-61369],[160270,681,-61369],[160435,346,-61369]]

def economy(path,uid):
 with closing(sqlite3.connect(path))as db:
  db.execute('BEGIN')
  return(db.execute('SELECT ed,experience FROM reward_balances WHERE uid=?',(uid,)).fetchone(),
      db.execute('SELECT *FROM inventory_items WHERE owner=?ORDER BY uid',(uid,)).fetchall())

def new_character(f,account):
 uid=r.f.Characters(f.config.state_file,account['id']).create('Ship'+str(account['id']),1,'ship-repair:'+str(account['id']))['uid']
 with closing(sqlite3.connect(f.config.state_file))as db,db:
  db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,))
  db.execute('UPDATE reward_balances SET experience=?WHERE uid=?',(client_data().thresholds[98],uid));ensure(db)
  db.execute('INSERT OR IGNORE INTO completed_quests VALUES(?,?,?,?)',(uid,26650,1,'{}'))
 return uid

def scene(s,group):
 run=s.dungeon_run;original=run.draw
 weights=SOURCE_NPC_GROUP_WEIGHTS[run.graph['source_sha256'],0,1]
 run.draw=lambda label,total:sum(weights[:group])if label=='group:0:1'else original(label,total)
 try:run._load_stage(0)
 finally:del run.draw
 run.part=1;run.next=None;run.ready_at=None;run.loaded()
 s.gate_stage=0;s.dungeon_substage_synced=True;s.gate_stage_loading=False;s.part_end_notified=False;s.defeated_npcs=run.defeated
 actors=[n for n in run.current['npcs']if n['template']in CONTROLLERS]
 assert len(actors)==4 and all(n['source_context'][5]==group for n in actors)
 return actors

def spawn_body(positions=POSITIONS,*,template=1375,creator=2**64-1,mode=0):
 raw=bytearray.fromhex(route_catalog()._data['spawn_seed']);struct.pack_into('<ii',raw,0,-1,template)
 dto=bytearray(resource_dto(raw));struct.pack_into('<Q',dto,0x6d,creator)
 for offset in(0x4e,0x54,0x61,0x65,0x66):dto[offset]=0
 dto[0x4e]=1
 rows=[]
 for xyz in positions:
  row=bytearray(dto);struct.pack_into('<fff',row,9,*xyz);rows.append(encode_npc(row,mode))
 return struct.pack('>I',len(rows))+b''.join(rows)

def death(npc,owners):
 return(struct.pack('>iBQQ6fBf',npc['key'],255,2**64-1,2**64-1,*([0.]*6),1,npc['hp'])
     +bytes(4)+struct.pack('>I',len(owners))+b''.join(struct.pack('>QB',uid,0)for uid in sorted(owners))+bytes(20))

def observe(peer):
 events=[];put=peer.pending.put_nowait
 def record(event):events.append(event);put(event)
 peer.pending.put_nowait=record
 return events

async def barrier(peer):
 await peer.send(0x48d);await peer.until(0x48f)

def assert_no_errors(f):
 assert not any(e['event']in('worker_error','notification_error','protocol_error')for e in f.events),f.events[-4:]

def parser_checks():
 for mode in(0,3):
  rows=summons._decode_rows(spawn_body(mode=mode),0,summons.LAYOUTS[str(mode)],(),validate=lambda dto,extra:None)
  assert [list(struct.unpack_from('<fff',dto,9))for dto,extra in rows]==POSITIONS
 for xyz in([100001,635,-61369],[10000000,635,-61369]):
  assert len(summons._decode_rows(spawn_body([xyz]),0,summons.LAYOUTS['0'],(),validate=lambda dto,extra:None))==1
 for xyz in([10000001,635,-61369],[float('nan'),0,0],[0,float('inf'),0]):
  diagnostic={}
  try:dungeon_spawns.decode(spawn_body([xyz]),lambda dto:None,diagnostic=diagnostic)
  except ValueError:pass
  else:raise AssertionError('Invalid position accepted')
  assert diagnostic['spawn_decode_failures'].get('location',0)>0
 return dict(original_positions=4,native_modes=[0,3],old_threshold_no_longer_rejects=True,nonfinite_and_outer_bound_refused=True)

async def solo():
 f=r.f.FriendsTests();await f.asyncSetUp()
 try:
  uid=new_character(f,f.alice);peer=await f.peer(f.alice);await peer.roster();await r.admit(peer,uid,33242)
  s=f.app.playing[f.alice['id']];events=observe(peer);before=economy(f.config.state_file,uid)
  await f.app.call(scene,s,0);run=s.dungeon_run
  keys=set(run.reserved_keys);initial_count=len(run.current['npcs']);wire=spawn_body();seq=peer.outgoing
  await peer.send(0x2ce,wire);assert(await peer.until(0x2cf)).payload==bytes(4);await peer.until(0x2d0)
  assert len(run.current['npcs'])==initial_count+4
  added=run.current['npcs'][-4:]
  assert len({n['key']for n in added})==4 and not keys.intersection(n['key']for n in added)
  # Same business request replay, without violating the transport's outer sequence.
  event=Event(0x202,kind=0x2ce,payload=wire,performers=(0,))
  replies=await f.app.call(s.handle,event,request_sequence=seq)
  assert [e.kind for e in replies]==[0x2cf]and replies[0].payload==bytes(4)
  assert len(run.current['npcs'])==initial_count+4
  for bad in(spawn_body(template=999999),spawn_body(creator=999999),spawn_body([[float('nan'),0,0]])):
   count=len(run.current['npcs']);requests=dict(run.dynamic_requests)
   await peer.send(0x2ce,bad);assert(await peer.until(0x2cf)).payload!=bytes(4)
   assert len(run.current['npcs'])==count and run.dynamic_requests==requests
  cached=s._spawn_diagnostic;old_decode=dungeon_spawns.decode
  dungeon_spawns.decode=lambda *a,**k:(_ for _ in()).throw(AssertionError('Diagnostic reparsed request'))
  try:
   diagnostic=dungeon_diagnostics.refusal(s,Event(0x202,kind=0x2ce),[],cached[0])
   assert diagnostic['spawn_decode_failures'].get('location',0)>0
   assert dungeon_diagnostics.refusal(s,Event(0x202,kind=0x2ce),[],cached[0]+1)['spawn_shape']=='not_decoded_by_scene_handler'
  finally:dungeon_spawns.decode=old_decode
  accepted=[]
  for group in range(3):
   actors=await f.app.call(scene,s,group)
   gate_keys={n['key']for n in run.current['npcs']if n['key_code']==1}
   for npc in actors:
    assert retire.source_rule(run,npc)is not None
    body=death(npc,[uid]);mark=len(events)
    await peer.send(0xad,body);assert(await peer.until(0xae)).payload==bytes(4);await peer.until(0xaf);await barrier(peer)
    assert run.defeated[npc['key']]==body and npc['active']is False
    notices=sum(e.kind==0xaf for e in events[mark:]if isinstance(e,Event))
    await peer.send(0xad,body);assert(await peer.until(0xae)).payload==bytes(4);await barrier(peer)
    assert sum(e.kind==0xaf for e in events[mark:]if isinstance(e,Event))==notices
    accepted.append(dict(group=group,template=npc['template'],source_index=npc['source_index']))
   assert not gate_keys.intersection(run.defeated)and not s.part_end_notified
  # Exact source pins remain mandatory, including an accepted actor's retry.
  npc=actors[0];original=copy.deepcopy(npc);rejected=[]
  for key,value in [('source_index',999),('hp',npc['hp']+1),('source_context',(999,*npc['source_context'][1:])),('points',[999]),('team',0),('dynamic',True)]:
   try:
    npc[key]=value
    try:rule=retire.source_rule(run,npc)
    except ValueError:rule=None
    assert rule is None,key;rejected.append(key)
   finally:npc.clear();npc.update(copy.deepcopy(original))
  assert economy(f.config.state_file,uid)==before;assert_no_errors(f)
  return dict(ok=True,original_source_declarations=len(accepted),accepted=accepted,spawned=4,
      replay_no_duplicate=True,invalid_template_owner_position_zero_mutation=True,source_mutations_refused=rejected,
      diagnostic_uses_actual_decode=True,no_gate_key_consumed=True,economy_unchanged=True)
 finally:await f.asyncTearDown()

async def shared():
 f=r.f.FriendsTests();await f.asyncSetUp()
 try:
  uids=[new_character(f,a)for a in(f.alice,f.bob)];a,b=uids
  f.config=replace(f.config,friends_coop_enabled=True);f.app.config=f.config;f.server.config=f.config
  alice,bob=await asyncio.gather(f.peer(f.alice),f.peer(f.bob));await asyncio.gather(alice.roster(),bob.roster())
  await alice.enter_town(a);await bob.enter_town(b)
  invitation=struct.pack('>Q',b)+wstring('Ship'+str(f.bob['id']))+struct.pack('>iBi',0,1,33242)+bytes(6)+wstring('')+bytes(15)
  await alice.send(0x136,invitation);await alice.until(0x137);await bob.until(0x138)
  await bob.send(0x139,struct.pack('>QQBiBQ',a,b,1,0,0,0));await bob.until(0x13a);await asyncio.gather(alice.until(0x13b),bob.until(0x13b))
  await f.coop_start(alice,bob,33242);await f.coop_load(alice,bob)
  sessions=list(f.app.playing.values());leader=f.app.playing[f.alice['id']];room=f.app.world.dungeons.room(leader)
  def setup():
   for s in sessions:scene(s,0)
   room.phase='active';friends_spawns.capture_static_origin(room)
  await f.app.call(setup);events={p:observe(p)for p in(alice,bob)}
  before={uid:economy(f.config.state_file,uid)for uid in uids};count=len(leader.dungeon_run.current['npcs']);wire=spawn_body()
  await bob.send(0x2ce,wire);assert(await bob.until(0x2cf)).payload!=bytes(4)
  assert all(len(s.dungeon_run.current['npcs'])==count for s in sessions)
  await alice.send(0x2ce,wire);assert(await alice.until(0x2cf)).payload==bytes(4)
  await asyncio.gather(alice.until(0x2d0),bob.until(0x2d0))
  assert all(len(s.dungeon_run.current['npcs'])==count+4 for s in sessions)
  assert [n['key']for n in sessions[0].dungeon_run.current['npcs']]==[n['key']for n in sessions[1].dungeon_run.current['npcs']]
  actors=[n for n in leader.dungeon_run.current['npcs']if n['template']in CONTROLLERS]
  npc=actors[0];body=death(npc,uids)
  await bob.send(0xad,body);await alice.send(0xad,death(npc,[a]));await barrier(alice)
  assert all(npc['key']not in s.dungeon_run.defeated for s in sessions)
  await alice.send(0xad,body);assert(await alice.until(0xae)).payload==bytes(4);await asyncio.gather(alice.until(0xaf),bob.until(0xaf))
  await barrier(alice);marks={p:len(events[p])for p in(alice,bob)}
  def next_part():
   for s in sessions:s.dungeon_run.part=2;s.dungeon_run.loaded()
   friends_spawns.advance(room)
   friends_spawns.capture_static_origin(room)
  await f.app.call(next_part)
  await alice.send(0xad,body);assert(await alice.until(0xae)).payload==bytes(4);await barrier(alice)
  assert all(not any(isinstance(e,Event)and e.kind==0xaf for e in events[p][marks[p]:])for p in(alice,bob))
  for npc in actors[1:]:
   late=death(npc,uids);await alice.send(0xad,late);assert(await alice.until(0xae)).payload==bytes(4)
   await asyncio.gather(alice.until(0xaf),bob.until(0xaf))
   assert all(s.dungeon_run.defeated[npc['key']]==late and s.dungeon_run.part==2 for s in sessions)
  assert all(economy(f.config.state_file,uid)==before[uid]for uid in uids);assert_no_errors(f)
  return dict(ok=True,participants=2,leader_spawn_broadcast=True,guest_spawn_and_retirement_refused=True,
      incomplete_readiness_refused=True,first_and_late_retirement_AE_empty_AF=True,late_retry_AE_only=True,economy_unchanged=True)
 finally:await f.asyncTearDown()

async def main():
 if SHARED_ONLY:return dict(ok=True,shared=await shared(),reused_parser_and_solo='first-TLS-run-partial.json',actual_authenticated_TLS=True,
     explicit_owned_scene_fixture=True,natural_route=False,natural_GUI=False,production_modified=False)
 return dict(ok=True,parser=parser_checks(),solo=await solo(),shared=await shared(),actual_authenticated_TLS=True,
     explicit_owned_scene_fixture=True,natural_route=False,natural_GUI=False,production_modified=False)

if __name__=='__main__':
 result={'ok':False}
 try:result=asyncio.run(main())
 except BaseException:result={'ok':False,'error':traceback.format_exc()};raise
 finally:(H/'ship-repairs-TLS.json').write_text(json.dumps(result,indent=2)+'\n','utf8');print(json.dumps(result))
