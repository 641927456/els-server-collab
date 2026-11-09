"""Held original LuCiel exit SQL cannot stall another account's native town position."""
import bootstrap,runtime_fixture as h
import asyncio,contextlib,json,os,psutil,sqlite3,struct,sys,threading,time,traceback
from unittest.mock import patch
from els_server.__main__ import _native_timing,_normal_scheduling
from els_server.domain import luciel_native_end
from els_server.storage import luciel_native_status
from els_server.storage.luciel_state import active_state,ensure_active
from els_server.protocol.luciel_end_messages import request
from els_server.dungeon_workers import _current
from mixed_role_seed import seed
psutil.Process().cpu_affinity([20,22]);_normal_scheduling()
variant=os.environ.get('ELS_LOAD_CANDIDATE_ROOT','candidate')=='solo-end-suite'
body=bytes.fromhex(json.loads((h.ROOT/'analysis/client-6c6b5180/end-request-native.json').read_bytes())['payload_hex']);active=request(body)
async def main():
 c=h.f.FriendsTests();await c.asyncSetUp();out=dict(ok=False,variant=variant,capacity_claim=False);release=threading.Event();entered=threading.Event();ownership=[]
 try:
  uid=seed(c,c.alice,'CapOwn1',True)
  with contextlib.closing(sqlite3.connect(c.config.state_file))as db,db:
   db.execute('BEGIN IMMEDIATE');ensure_active(db);db.execute('INSERT OR REPLACE INTO luciel_active_states VALUES(?,?,0)',(uid,1-active))
  bob=await c.peer(c.bob);await bob.roster();await bob.enter_town(c.app.accounts[c.bob['id']].uid)
  witness_account=c.app.registry.create('endwitness');witness=await c.peer(witness_account);await witness.roster();await witness.enter_town(c.app.accounts[witness_account['id']].uid)
  alice=await c.peer(c.alice);await alice.roster();await alice.enter_town(uid);s=c.app.playing[c.alice['id']]
  with c.app.dungeon_workers.scope(s),c.app.world_lock:h.room(s)
  from els_server.protocol.protocol_codec import Event
  assert c.app.dungeon_workers.solo_transition(s.handle,(Event(0x202,kind=0x67),))
  def saved():
   with contextlib.closing(sqlite3.connect(c.config.state_file))as db:
    cursor=db.execute('SELECT session_id,epoch,sequence,request_hash FROM luciel_status_cursors WHERE uid=?',(uid,)).fetchone()if luciel_native_status.present(db,luciel_native_status.CURSORS)else None
    return active_state(db,uid),cursor
  before=saved();perform=luciel_native_status.perform;late_failures=[]
  def failing(*args,**kwargs):
   validate=kwargs['validate'];calls=0
   def checked():
    nonlocal calls
    calls+=1;validate()
    if calls==3:late_failures.append(True);raise ValueError('Owned post-write lease failure')
   kwargs['validate']=checked
   return perform(*args,**kwargs)
  with patch.object(luciel_native_status,'perform',failing),c.app.dungeon_workers.scope(s),c.app.world_lock:
   assert luciel_native_end.handle(s,Event(0x202,kind=0x67,payload=body,performers=(0,)),alice.outgoing)==[]
  assert late_failures==[True]and saved()==before and s.phase=='dungeon_active'and s.dungeon_end_payload is None
  expected={e.kind:e.payload for e in luciel_native_end.replies(s,active)};perform=luciel_native_status.perform
  def held(*args,**kwargs):
   current=_current.get();ownership.append(dict(world_owned=c.app.world_lock._is_owned(),account_domain_owned=current is not None and current[0]is s and current[1].lock._is_owned()))
   entered.set();assert release.wait(5),'Owned solo end was not released'
   return perform(*args,**kwargs)
  with patch.object(luciel_native_status,'perform',held):
   await alice.send(0x67,body)
   async with asyncio.timeout(5):
    while not entered.is_set():await asyncio.sleep(.002)
   while not witness.pending.empty():witness.pending.get_nowait()
   await bob.send(0x22b,struct.pack('>fffIBBHBii?i',37.,0.,time.perf_counter()%1024,0,0,0,0,0,0,0,False,0))
   move=asyncio.create_task(witness.until(0x22e))
   try:
    if variant:
     notice=await asyncio.wait_for(asyncio.shield(move),1)
     assert not release.is_set()and int.from_bytes(notice.payload[:8],'big')==c.app.accounts[c.bob['id']].uid
    else:
     await asyncio.sleep(.15);assert not move.done(),'Control did not reproduce the inner world lock'
   finally:release.set()
   await move
   for kind,payload in expected.items():assert(await alice.until(kind)).payload==payload
  assert ownership==[dict(world_owned=not variant,account_domain_owned=True)],ownership
  cold=saved();assert cold[0]['active_unit']==active and cold[0]['revision']==before[0]['revision']+1 and cold[1][1]==s.reward_run_id and s.phase=='map_loading'and s.dungeon_return_pending
  await alice.send(0x67,body);assert(await alice.until(0x68)).payload==expected[0x68]and saved()==cold
  await alice.send(0x225,struct.pack('>iB',20000,0));await alice.until(0x226)
  await alice.send(0x227,struct.pack('>fffBH',1.,2.,3.,0,0));await alice.until(0x228)
  assert s.phase=='town_ready'and s in c.app.world.members
  out.update(ok=True,slow_original_exit_SQL_world_owned=not variant,town_peer_delivered_while_exit_SQL_held=variant,account_domain_retained=True,native_reply_payloads_exact=True,cold_active_and_cursor_committed=True,late_validation_failure_rolls_back_SQL_and_actor=True,duplicate_end_has_no_new_write=True,normal_native_town_return=True)
 except BaseException as error:out.update(error=repr(error),traceback=traceback.format_exc())
 finally:
  release.set();await c.asyncTearDown();out.update(source=bootstrap.SOURCE_BINDINGS,owned_runtime_removed=not c.root.exists(),connections=len(c.server.connections),GIL_enabled=sys._is_gil_enabled(),errors=[r['event']for r in c.events if r['event']in('worker_error','notification_error','connection_task_error')])
  out['ok']=out['ok']and out['owned_runtime_removed']and not out['connections']and not out['errors']
  (h.H/('native-solo-end-'+('variant'if variant else'control')+'.json')).write_text(json.dumps(out,indent=2),'utf8')
 print(json.dumps({k:v for k,v in out.items()if k!='source'}));return out['ok']
with _native_timing():raise SystemExit(not asyncio.run(main()))
