"""Private real Application/TLS loading, with owned progress fixtures only."""
import source
from pathlib import Path
from source import HERE,BASE,CHANNEL
import asyncio,contextlib,importlib.util,json,os,sqlite3,struct,traceback
from unittest.mock import patch
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
fixture=load('fatigue_tls_fixture',Path(__file__).resolve().parent/'friends_fixture.py')
from els_server.protocol.protocol_codec import Event,encode_event,encode_frame
from els_server.domain import normal_fatigue_rules as rules,normal_fatigue_flow as flow
from els_server.storage import normal_fatigue as storage
async def send(self,kind,payload=b'',event_id=0x202):
 if kind==0x5bf and not payload:payload=bytes(8)
 self.writer.write(encode_frame(encode_event(Event(event_id,kind=kind,payload=payload,performers=(0,))),self.keys,spi=self.spi,sequence=self.outgoing));self.outgoing+=1;await self.writer.drain()
fixture.Peer.send=send
load('fatigue_native_reader',Path(__file__).resolve().parent/'native_fixture_reader.py').install(fixture)
OPAQUE=bytes.fromhex('eefc726aad751f003e6b6d2e0c4d36e2923600000010332b6d21282a5c1774790f0f3a4c7947')
async def barrier(peer):await peer.send(0x48d);await peer.until(0x48f)

async def scenario(group):
 case=fixture.FriendsTests();await case.asyncSetUp();root=case.root;passed=False;checks=[]
 def sql(query,args=()):
  with contextlib.closing(sqlite3.connect(case.config.state_file))as db,db:return db.execute(query,args).fetchall()
 def state():return sql('SELECT owner,current,revision FROM normal_fatigue_state ORDER BY owner')
 try:
  if group:
   alice,bob,uid,other_uid=await case.coop_pair();peers=(alice,bob)
  else:
   alice=await case.peer(case.alice);await alice.roster();uid=case.app.accounts[case.alice['id']].uid;await alice.enter_town(uid);peers=(alice,)
  actors=tuple(case.app.playing.values())
  for actor in actors:
   sql('UPDATE characters SET level=99,revision=revision+1 WHERE uid=?',(actor.account.uid,))
  mid=33202;r=rules.route(mid)
  if group:
   await alice.send(0x145,struct.pack('>ibb',mid,0,0));assert(await alice.until(0x146)).payload==bytes(4)
   await asyncio.gather(*(barrier(p)for p in peers));await case.coop_start(alice,bob,identity=mid)
  else:
   await alice.send(0x7d4,struct.pack('>ii',1,mid));assert(await alice.until(0x7d5)).payload[:4]==bytes(4)
   await alice.send(0x382,OPAQUE);await alice.until(0x14a);await alice.send(0x91,struct.pack('>ii',100,0));await alice.until(0xb2)
  session=next(s for s in actors if s.account.uid==uid);assert session.dungeon_run.identity==mid
  async def loaded():
   for p in peers:await p.send(0xb3,bytes(9));await p.until(0xb4)
   await asyncio.gather(*(p.until(0xbd)for p in peers));await asyncio.gather(*(barrier(p)for p in peers))
  before=state()
  if group:
   await alice.send(0xb3,bytes(9));await alice.until(0xb4);await barrier(alice);assert state()==before
   original=storage._apply
   def fail_second(db,path,owner,*args,**kwargs):
    if owner==other_uid:raise ValueError('owned second member writer failure')
    return original(db,path,owner,*args,**kwargs)
   with patch.object(storage,'_apply',fail_second):await bob.send(0xb3,bytes(9));await barrier(bob)
   assert state()==before and all(not s.dungeon_substage_synced for s in actors)
   await bob.send(0xb3,bytes(9));await bob.until(0xb4)
   await asyncio.gather(*(p.until(0xbd)for p in peers));await asyncio.gather(*(barrier(p)for p in peers))
   checks.append('actual-group-barrier-second-member-failure-no-increment-then-retry')
  else:await loaded()
  first=r['stage_costs'][str(session.dungeon_run.stage)]
  assert all(row[1]==4800-first for row in state()),state()
  initial=state();await alice.send(0xb3,bytes(9));await alice.until(0xb4);await barrier(alice);assert state()==initial
  checks+=['native-first-load-stage-share','duplicate-B3-no-debit']
  seen={session.dungeon_run.stage};subparts=0;transitions=0
  while len(seen)<2 or subparts==0:
   assert transitions<12
   run=session.dungeon_run
   def qualify():
    for member in actors:
     rr=member.dungeon_run
     for npc in rr.current['npcs']:
      rr.defeated[npc['key']]=(struct.pack('>iBQQ6fBf',npc['key'],0,uid,uid,0.,0.,0.,1.,2.,3.,0,npc['hp'])+struct.pack('>IQf',1,uid,1.)+struct.pack('>IQB',1,uid,1)+bytes(8)+bytes(4)+struct.pack('>Q',uid))
     rr.portal_requested=True;assert rr.poll_ready();member.part_end_notified=True
    if group:case.app.world.dungeons.room(session).phase='part_end'
   await case.app.call(qualify);target=dict(run.next);part=run.part;assert target['kind']!=4
   before=state()
   for p in peers:await p.send(0xbb,struct.pack('>b',part));await p.until(0xbc)
   if target['kind']==0:
    subparts+=1;await asyncio.gather(*(p.until(0xbd)for p in peers))
   else:
    await asyncio.gather(*(p.until(0xb2)for p in peers));await loaded();seen.add(run.stage)
   await asyncio.gather(*(barrier(p)for p in peers))
   expected=4800-sum(r['stage_costs'][str(st)]for st in seen)
   assert all(row[1]==expected for row in state()),(target,before,state(),expected)
   transitions+=1
  checks.append('actual-subpart-no-debit-and-next-stage-share')
  saved=state()
  for p in peers:await p.close()
  async with asyncio.timeout(8):
   while case.app.playing:await asyncio.sleep(.03)
  assert state()==saved
  peer=await case.peer(case.alice);await peer.roster();await peer.enter_town(uid);await barrier(peer);assert state()==saved
  checks.append('disconnect-cold-login-retains-correct-fatigue')
  assert not [e for e in case.events if e['event']in('worker_error','protocol_error','connection_task_error')]
  passed=True
 except BaseException:
  (HERE/f'tls-failure-{CHANNEL}-{"group"if group else"solo"}.json').write_text(json.dumps(dict(traceback=traceback.format_exc(),checks=checks,stage=session.dungeon_run.stage if 'session'in locals()and session.dungeon_run else None,events=[{k:e[k]for k in ('event','error','reason','detail')if k in e}for e in case.events[-30:]]),ensure_ascii=False,indent=2),encoding='utf8')
  raise
 finally:
  await case.asyncTearDown()
  result=dict(ok=passed,channel=CHANNEL,group=group,checks=checks,actual_Application_TLS=True,owned_progress_fixture=True,natural_GUI=False,online_installed=False,cleanup=dict(owned_runtime_removed=not root.exists(),active_connections=len(case.server.connections)))
  (HERE/f'qa-tls-{CHANNEL}-{"group"if group else"solo"}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 return result
async def main():
 results=[await scenario(False),await scenario(True)];print(json.dumps(results))
if __name__=='__main__':asyncio.run(main())
