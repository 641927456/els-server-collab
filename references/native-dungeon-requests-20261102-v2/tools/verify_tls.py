"""Owned Application/TLS dispatch checks with explicit controlled source rooms."""
from pathlib import Path
from contextlib import closing
import ast,asyncio,copy,importlib.util,json,os,sqlite3,struct,sys,tempfile,traceback,uuid
O=Path(__file__).resolve().parent;R=Path('G:/els')
sys.path[:0]=[str(R/'releases/local/local-native-atlas-scroll-support-20261101-v1'),str(R/'tools')]
sys.dont_write_bytecode=True
(O/'tmp').mkdir(exist_ok=True);tempfile.tempdir=str(O/'tmp');os.environ.pop('ELS_TEST_CERT_DIR',None)
import els_server.domain
els_server.domain.__path__.insert(0,str(O/'candidate/els_server/domain'))
from els_server.domain.dungeon_routes import DungeonRun
from els_server.domain.dungeon_clock import DungeonClock
from els_server.domain.town_travel import catalog as towns
from els_server.domain.friends_spawns import capture_static_origin
from els_server.protocol.protocol_codec import Event,encode_event,encode_frame,decode_event,decode_frame
spec=importlib.util.spec_from_file_location('owned_variant_peer',R/'tests/test_friends_server.py')
t=importlib.util.module_from_spec(spec);sys.modules[spec.name]=t;spec.loader.exec_module(t)
prior=R/'analysis/monster-economy-formal-20261025-v1/verify_native.py'
node=next(n for n in ast.parse(prior.read_text('utf8')).body if isinstance(n,ast.ClassDef)and n.name=='Peer')
exec(compile(ast.Module(body=[node],type_ignores=[]),str(prior),'exec'))
class NativePeer(Peer):
 async def send(self,kind,payload=b'',event_id=0x202):
  if kind not in (0xb8,0x471,0x30a):return await super().send(kind,payload,event_id)
  event=Event(event_id,kind=kind,payload=payload,performers=(0,))
  self.writer.write(encode_frame(encode_event(event),self.keys,spi=self.spi,sequence=self.outgoing));self.outgoing+=1;await self.writer.drain()
t.Peer=NativePeer

async def main():
 c=t.FriendsTests();await c.asyncSetUp();out=dict(ok=False,actual_Application_TLS=True,controlled_source_rooms=True,natural_GUI=False,natural_battle=False)
 try:
  # Real authenticated peers, town entry, party invitation and ordinary admission.
  alice,bob,a,b=await c.coop_pair();await c.coop_start(alice,bob);await c.coop_load(alice,bob)
  sessions=(c.app.playing[c.alice['id']],c.app.playing[c.bob['id']]);dispatcher=c.app.world.dungeons;room=dispatcher.room(sessions[0])
  snapshots=await c.app.call(lambda:[copy.deepcopy(s.account.get_inventory_snapshot())for s in sessions])
  def source(identity,stage,part,cleared=False):
   # Controlled source checkpoint, not a claim of natural admission/combat here.
   room.identity=identity;room.phase='active';room.ended.clear();room.portals.clear();room.previous_part=None
   for s in sessions:
    run=DungeonRun(identity,room.seed,internal=True);run._load_stage(stage);run.part=part;run.loaded()
    if cleared:run.defeated={n['key']:b'controlled accepted combat checkpoint'for n in run.current['npcs']if n['active']}
    s.dungeon_run=run;s.defeated_npcs=run.defeated;s.dungeon_clock=DungeonClock();s.gate_stage=stage
    s.dungeon_substage_synced=True;s.gate_stage_loading=False;s.part_end_notified=False;s.clear_notified=False;s.dungeon_failed=False
    s.reward_run_id=str(uuid.uuid5(uuid.UUID(room.seed),'reward:'+str(s.account.uid)))
   if hasattr(room,'shared_actors'):del room.shared_actors
   capture_static_origin(room)
  await c.app.call(lambda:source(33342,0,0))
  for peer in (alice,bob):
   await peer.send(0xb8,b'\0');assert(await peer.until(0xb9)).payload==bytes(4)
  assert await c.app.call(lambda:all(not s.dungeon_run.portal_requested and not s.part_end_notified for s in sessions))
  # Native contact, both original delay and room-wide clear notification.
  await c.app.call(lambda:source(33342,1,2,True))
  raw=struct.pack('>iiHI',1,2,0,1)+b'\1\0'
  await alice.send(0x471,raw)
  for peer in (alice,bob):assert struct.unpack('>7i',(await peer.until(0x472)).payload)==(0,1,0,1,2,0,0)
  for peer in (alice,bob):await peer.until(0xba)
  assert await c.app.call(lambda:all(s.dungeon_run.portal_requested and s.part_end_notified for s in sessions))
  # Real transport dispatch of a member's line contact to both native consumers.
  await c.app.call(lambda:source(34090,1,0))
  await bob.send(0x30a,bytes(4));assert(await bob.until(0x30b)).payload==bytes(4)
  for peer in (alice,bob):assert(await peer.until(0x30c)).payload==bytes(4)
  await alice.send(0x30a,struct.pack('>i',999999));assert(await alice.until(0x30b)).payload==struct.pack('>i',-1)
  assert await c.app.call(lambda:[s.account.get_inventory_snapshot()for s in sessions]==snapshots)
  assert await c.app.call(lambda:all((s.dungeon_run.stage,s.dungeon_run.part)==(1,0)and not s.dungeon_run.defeated for s in sessions))
  errors=[e['event']for e in c.events if e['event']in('worker_error','protocol_error','connection_error')];assert not errors,errors
  out.update(ok=True,cases=['native B8 before kills: leader and member','native 471 -> 472 -> delayed BA: both peers','member native 30A -> own 30B and both 30C','unknown activation rejected'],inventory_unchanged=True,trigger_no_HP_kill_or_cursor_change=True)
 except Exception as error:out.update(error=repr(error),traceback=traceback.format_exc(limit=12),server_error_kinds=[e['event']for e in c.events if e['event']in('worker_error','protocol_error','connection_error')])
 finally:await c.asyncTearDown()
 (O/'server-TLS.json').write_text(json.dumps(out,indent=2)+'\n','utf8');print(json.dumps(out));assert out['ok']
asyncio.run(main())
