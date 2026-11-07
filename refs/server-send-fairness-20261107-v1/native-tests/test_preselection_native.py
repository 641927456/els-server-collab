"""Real TLS admission cannot hold unrelated town actors behind slow roster SQL."""
import bootstrap,runtime_fixture as h
import asyncio,json,os,psutil,struct,sys,threading,time,traceback
from unittest.mock import patch
from els_server.__main__ import _native_timing,_normal_scheduling
from els_server.domain.local_session import LocalSession,LocalAccount
from els_server.dungeon_workers import _current
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import character_list
from els_server.storage.character_selection import snapshot
psutil.Process().cpu_affinity([20,22]);_normal_scheduling()
variant=os.environ.get('ELS_LOAD_CANDIDATE_ROOT','candidate')=='preselection-suite'
async def main():
 c=h.f.FriendsTests();await c.asyncSetUp();out=dict(ok=False,variant=variant,capacity_claim=False);release=threading.Event();entered=threading.Event();reads=[];actors={}
 try:
  bob=await c.peer(c.bob);await bob.roster();await bob.enter_town(c.app.accounts[c.bob['id']].uid)
  witness_account=c.app.registry.create('witness');witness=await c.peer(witness_account);await witness.roster();await witness.enter_town(c.app.accounts[witness_account['id']].uid)
  alice=await c.peer(c.alice);original=LocalAccount.character_list;handle=LocalSession.handle
  def capture(session,event,*args,**kwargs):
   if session.identity['id']==c.alice['id']and event.kind in(0x1e,0x35,0x1ef,0x39,0x485,0x490):
    actors['last']=session
    current=_current.get();reads.append(dict(kind=event.kind,phase=session.phase,world_owned=c.app.world_lock._is_owned(),account_domain_owned=current is not None and current[0]is session and current[1].lock._is_owned()))
   return handle(session,event,*args,**kwargs)
  def held(account,*args,**kwargs):
   if account.account_id==c.alice['id']:
    entered.set();assert release.wait(5),'Owned roster query not released'
   return original(account,*args,**kwargs)
  with patch.object(LocalSession,'handle',capture),patch.object(LocalAccount,'character_list',held):
   for request,response in((0x1a,0x1b),(0x1e,0x19c),(0x35,0x36),(0x1ef,0x1f0),(0x39,0x3a)):
    await alice.send(request);await alice.until(response)
   await alice.send(0x485)
   async with asyncio.timeout(5):
    while not entered.is_set():await asyncio.sleep(.002)
   while not witness.pending.empty():witness.pending.get_nowait()
   payload=struct.pack('>fffIBBHBii?i',23.,0.,time.perf_counter()%1024,0,0,0,0,0,0,0,False,0)
   await bob.send(0x22b,payload)
   move=asyncio.create_task(witness.until(0x22e))
   try:
    if variant:
     notice=await asyncio.wait_for(asyncio.shield(move),1)
     assert not release.is_set()and int.from_bytes(notice.payload[:8],'big')==c.app.accounts[c.bob['id']].uid
    else:
     await asyncio.sleep(.15);assert not move.done(),'Control did not reproduce world-lock blockage'
   finally:release.set()
   await move;reply=await alice.until(0x488)
   account=c.app.accounts[c.alice['id']]
   expected=character_list('dx11_260923',characters=original(account),selection=snapshot(account.characters.path,account.account_id))
   assert reply.payload==expected.payload
   await alice.send(0x490);await alice.until(0x491)
   # Both native roster variants remain in the original state machine: refresh
   # after channels, and reconnect skipping terms already accepted by this account.
   await alice.send(0x485);assert(await alice.until(0x488)).payload==expected.payload
   await alice.send(0x490);await alice.until(0x491)
   await alice.close();c.peers.remove(alice)
   alice=await c.peer(c.alice)
   for request,response in((0x1a,0x1b),(0x1e,0x19c),(0x35,0x36),(0x1ef,0x1f0),(0x485,0x488),(0x490,0x491)):
    await alice.send(request);answer=await alice.until(response)
    if request==0x485:assert answer.payload==expected.payload
  assert len(reads)==13 and all(row['account_domain_owned']for row in reads),reads
  assert all(row['world_owned']is(not variant)for row in reads),reads
  s=actors['last'];workers=c.app.dungeon_workers
  event=Event(0x202,kind=0x485)
  phase=s.phase;s.phase='terms_ready'
  assert workers.town_preparation(s.handle,(event,))is variant
  c.app.playing[s.identity['id']]=c.app.playing[c.bob['id']]
  try:assert not workers.town_preparation(s.handle,(event,))
  finally:c.app.playing.pop(s.identity['id'])
  s.phase='town_ready';assert not workers.town_preparation(s.handle,(event,))
  s.phase='terms_ready';role=s.role;s.role='frontend';assert not workers.town_preparation(s.handle,(event,));s.role=role
  assert not workers.town_preparation(s.handle,(Event(0x402,kind=0x485),))
  s.phase=phase
  out.update(ok=True,handler_lock_observations=reads,slow_roster_reproduces_blockage=not variant,town_peer_delivered_while_roster_held=variant,roster_payload_matches_original=True,native_refresh_and_accepted_terms_reconnect=True,active_account_frontend_invalid_event_keep_original_route=True)
 except BaseException as error:out.update(error=repr(error),traceback=traceback.format_exc())
 finally:
  release.set();await c.asyncTearDown();out.update(source=bootstrap.SOURCE_BINDINGS,owned_runtime_removed=not c.root.exists(),connections=len(c.server.connections),GIL_enabled=sys._is_gil_enabled(),errors=[r['event']for r in c.events if r['event']in('worker_error','notification_error','connection_task_error')])
  out['ok']=out['ok']and out['owned_runtime_removed']and not out['connections']and not out['errors']
  (h.H/('native-preselection-'+('variant'if variant else'control')+'.json')).write_text(json.dumps(out,indent=2),'utf8')
 print(json.dumps({k:v for k,v in out.items()if k!='source'}));return out['ok']
with _native_timing():raise SystemExit(not asyncio.run(main()))
