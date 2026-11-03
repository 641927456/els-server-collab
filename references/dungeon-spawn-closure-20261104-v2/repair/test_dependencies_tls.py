"""Actual two-peer Application/TLS; late raid phases are explicit owned fixtures."""
import asyncio,hashlib,importlib.util,json,os,struct,sys,tempfile,traceback,uuid
from pathlib import Path
W=Path(__file__).resolve().parent;ROOT=W.parents[3];D=W/'runtime';M=json.loads((W/'candidate-manifest.json').read_bytes())
sys.dont_write_bytecode=True;sys.path[:0]=[str(D),str(ROOT/'tools')];tempfile.tempdir=str(W)
os.environ['ELS_TEST_CERT_DIR']=str(ROOT/'analysis/luciel-natural-dynamic-passive-01a1531c-20261020-v1/party-UI-r10/tls')
import els_server,els_server.domain,els_server.protocol,els_server.storage
assert Path(els_server.__file__).is_relative_to(D)
sp=importlib.util.spec_from_file_location('spawn_tls_fixture',ROOT/'tests/test_friends_server.py');t=importlib.util.module_from_spec(sp);sp.loader.exec_module(t)
sp=importlib.util.spec_from_file_location('continuous_reader',ROOT/'analysis/server-realtime-isolation-20261102-v1/native_fixture_reader.py');rr=importlib.util.module_from_spec(sp);sp.loader.exec_module(rr);rr.install(t)
from els_server.domain.dungeon_routes import DungeonRun
from els_server.domain.dungeon_npcs import encode_npc
from els_server.protocol.protocol_codec import Event,encode_event,encode_frame
async def send(self,kind,payload=b'',event_id=0x202):
 if kind==0x5bf and not payload:payload=bytes(8)
 self.writer.write(encode_frame(encode_event(Event(event_id,kind=kind,payload=payload,performers=(0,))),self.keys,spi=self.spi,sequence=self.outgoing));self.outgoing+=1;await self.writer.drain()
t.Peer.send=send
def payload(tid,creator):
 raw=bytearray(0xa4);struct.pack_into('<ii',raw,0,-1,tid);struct.pack_into('<fff',raw,9,123.,456.,789.);raw[0x4e]=1;struct.pack_into('<Q',raw,0x6d,creator)
 return struct.pack('>I',1)+encode_npc(raw,0)
async def main():
 c=t.FriendsTests();await c.asyncSetUp();out=dict(ok=False,actual_Application_TLS=True,actual_two_peer_room=True,explicit_late_phase_fixtures=True,natural_raid_combat=False)
 try:
  alice,bob,a,b=await c.coop_pair();await c.coop_start(alice,bob);await c.coop_load(alice,bob)
  s=c.app.playing[c.alice['id']];guest=c.app.playing[c.bob['id']];dispatcher=c.app.world.dungeons;room=dispatcher.room(s)
  before={m.account.uid:m.account.get_reward_balances()for m in room.members};results=[]
  for chain in M['dependency_paths']:
   def phase():
    room.identity=chain['dungeon'];room.seed=str(uuid.uuid4());room.phase='active';room.shared_actors=None
    for m in room.members:
     run=DungeonRun(chain['dungeon'],room.seed);run._load_stage(chain['stage']);run.part=next(part for part,p in run.parts.items()if any(n['template']==chain['root']for n in p['npcs']))
     m.dungeon_run=run;m.enter_dungeon=chain['dungeon'];m.phase='dungeon_active';m.population_test=True;m.dungeon_substage_synced=True;m.clear_notified=False;m.part_end_notified=False
    return next(n['key']for n in s.dungeon_run.current['npcs']if n['template']==chain['root'])
   creator=await c.app.call(phase)
   # Guests cannot act as the original room-master AI creator.
   count=len(s.dungeon_run.current['npcs']);await bob.send(0x2ce,payload(chain['edges'][0]['target'],creator));ack=await bob.until(0x2cf);assert ack.payload==struct.pack('>i',1)
   assert len(s.dungeon_run.current['npcs'])==count and len(guest.dungeon_run.current['npcs'])==count
   for edge in chain['edges']:
    await alice.send(0x2ce,payload(edge['target'],creator));ack=await alice.until(0x2cf);assert ack.payload==bytes(4),(chain,ack.payload.hex())
    own,remote=await asyncio.gather(alice.until(0x2d0),bob.until(0x2d0));assert own.payload==remote.payload
    actor=s.dungeon_run.current['npcs'][-1];other=guest.dungeon_run.current['npcs'][-1]
    assert actor==other and actor['template']==edge['target']and actor['hp']>0 and actor['no_drop']
    assert actor['wire']in own.payload and actor['init']in own.payload;creator=actor['key']
   # Mixed bad batch cannot partially add an admitted actor to either view.
   good=payload(chain['target'],creator)[4:];bad=payload(2147483647,creator)[4:]
   count=len(s.dungeon_run.current['npcs']);await alice.send(0x2ce,struct.pack('>I',2)+good+bad);ack=await alice.until(0x2cf);assert ack.payload==struct.pack('>i',1)
   assert all(len(m.dungeon_run.current['npcs'])==count and not m.dungeon_run.defeated and not m.clear_notified and not m.part_end_notified for m in room.members)
   assert before=={m.account.uid:m.account.get_reward_balances()for m in room.members}
   results.append(dict(dungeon=chain['dungeon'],stage=chain['stage'],target=chain['target'],source_chain=[e['producer']for e in chain['edges']]+[chain['target']],actual_2D0_broadcast_equal=True,guest_rejected=True,mixed_bad_batch_atomic=True,initialization_bytes=len(actor['init'])))
  assert len(results)==len(M['dependency_paths'])
  errors=[e for e in c.events if e['event']in('worker_error','notification_error','connection_task_error')];assert not errors,errors
  out.update(ok=True,cases=results,reward_balances_unchanged=True,no_gate_or_clear_fabricated=True)
 except Exception as exc:
  out.update(error=repr(exc),traceback=traceback.format_exc(),errors=[e for e in c.events if e['event']in('dungeon_refusal','worker_error','protocol_error','connection_task_error')])
 finally:
  await c.asyncTearDown();out['owned_database_removed']=not c.root.exists();(W/'dependency-TLS-tests.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf8')
 print(json.dumps(out));return out['ok']
if __name__=='__main__':sys.exit(not asyncio.run(main()))
