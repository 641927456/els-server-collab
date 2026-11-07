"""Native metadata ACK equivalence, queued/running peer delivery and creation barrier."""
import bootstrap,runtime_fixture as h
import asyncio,contextlib,json,sqlite3,struct,sys,threading,time,traceback
from unittest.mock import patch
from els_server.domain import local_session as local
from els_server.__main__ import _normal_scheduling,_native_timing
from profile_town import seed
_normal_scheduling()
async def until(predicate,seconds=5):
 async with asyncio.timeout(seconds):
  while not predicate():await asyncio.sleep(.001)
async def move(peer,value):
 await peer.send(0x22b,struct.pack('>fffIBBHBii?i',float(value),0.,time.perf_counter()%1024,0,0,0,0,0,0,0,False,0))
async def receive_move(peer,uid,value):
 async with asyncio.timeout(.5):
  while True:
   e=await peer.until(0x22e)
   if struct.unpack_from('>Qf',e.payload)==(uid,float(value)):return
async def main():
 c=h.f.FriendsTests();await c.asyncSetUp();out=dict(ok=False,checks={},source=bootstrap.SOURCE_BINDINGS);release=threading.Event()
 try:
  charlie=c.app.registry.create('own_meta_third');ids=[c.alice,c.bob,charlie]
  uids=[seed(c,v,'OwnMeta'+str(i),False)for i,v in enumerate(ids)]
  peers=[await c.peer(v)for v in ids];a,b,d=peers
  for peer in peers:await peer.roster()
  await a.enter_town(uids[0]);await b.enter_town(uids[1]);actor=c.app.playing[c.alice['id']]
  def cold():
   with contextlib.closing(sqlite3.connect(c.config.state_file))as db:
    return db.execute('SELECT uid,ed,experience FROM reward_balances ORDER BY uid').fetchall()
  before=cold();original=local.responses;entered=threading.Event();calls=[]
  def responses(kind,*args,**kwargs):
   if kind==0x48d and kwargs.get('account_id')==c.alice['id']:
    calls.append(dict(character_argument_supplied='character'in kwargs));entered.set();assert release.wait(5),'Owned metadata hold exceeded'
   return original(kind,*args,**kwargs)
  with patch.object(local,'responses',responses):
   gate=c.app.economy.account_lock(c.alice['id']);await gate.acquire()
   try:
    await a.send(0x48d);await until(lambda:actor._peer_drain_open)
    await move(b,741);await receive_move(a,uids[1],741);assert not entered.is_set()
    out['checks']['peer_moves_pass_while_metadata_waits_for_account_admission']=True
   finally:gate.release()
   await until(entered.is_set)
   await move(b,742);await receive_move(a,uids[1],742);assert not release.is_set()
   out['checks']['peer_moves_pass_while_metadata_handler_is_held']=True
   await d.enter_town(uids[2])
   await move(b,743);await b.send(0x48d);await b.until(0x48f);await asyncio.sleep(.03)
   seen_creation=False;seen_move=False
   async with asyncio.timeout(.5):
    while not seen_move:
     e=await a.pending.get()
     if isinstance(e,Exception):raise e
     if e.kind==0x22a:seen_creation=True
     if e.kind==0x22e and struct.unpack_from('>Qf',e.payload)==(uids[1],743.):
      assert seen_creation;seen_move=True
   out['checks']['member_creation_still_precedes_following_coordinate']=True
   assert not release.is_set()
   release.set();ack=await a.until(0x48f)
   expected=original(0x48d,actor.client_build,account_id=c.alice['id'])[0]
   assert ack==expected and calls==[dict(character_argument_supplied=False)]
   out['checks']['original_native_metadata_ACK_exact_without_unused_character_projection']=True
  assert cold()==before;out['checks']['metadata_does_not_change_wallet_or_EXP']=True;out['ok']=True
 except BaseException as error:out.update(error=repr(error),traceback=traceback.format_exc())
 finally:
  release.set();await c.asyncTearDown();out.update(owned_runtime_removed=not c.root.exists(),connections=len(c.server.connections),errors=[r for r in c.events if r['event']in('worker_error','notification_error','connection_task_error')],GIL_enabled=sys._is_gil_enabled())
  out['ok']=out['ok']and out['owned_runtime_removed']and not out['connections']and not out['errors']
  (bootstrap.HERE/'metadata-peer-native.json').write_text(json.dumps(out,indent=2),'utf8')
 print(json.dumps({k:v for k,v in out.items()if k!='source'}));return out['ok']
with _native_timing():raise SystemExit(not asyncio.run(main()))
