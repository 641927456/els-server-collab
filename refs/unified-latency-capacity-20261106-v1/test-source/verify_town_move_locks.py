"""Original actual handlers, native mailbox bytes and shared admission counts."""
import runtime_fixture as h
import ast,asyncio,contextlib,importlib,json,sqlite3,struct,sys,threading,time
from unittest.mock import patch
from profile_town import seed
from els_server.application import FriendsSession
from els_server.dungeon_workers import DungeonWorkers
from els_server.protocol.protocol_codec import Event
app_module=importlib.import_module('els_server.application');workers_module=importlib.import_module('els_server.dungeon_workers')
def original_method(relative,klass,name,module):
 tree=ast.parse((h.H/'candidate/els_server'/relative).read_bytes());cl=next(n for n in tree.body if isinstance(n,ast.ClassDef)and n.name==klass)
 node=next(n for n in cl.body if isinstance(n,ast.FunctionDef)and n.name==name)
 class Super(ast.NodeTransformer):
  def visit_Call(self,n):
   self.generic_visit(n)
   if isinstance(n.func,ast.Name)and n.func.id=='super'and not n.args:n.args=[ast.Name(id=klass,ctx=ast.Load()),ast.Name(id='self',ctx=ast.Load())]
   return n
 node=Super().visit(node);scope=dict(vars(module));exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),'owned-original-'+name,'exec'),scope);return scope[name]
class Counter:
 def __init__(self,lock):self.lock=lock;self.local=threading.local();self.count=0
 def acquire(self,*args,**kwargs):
  result=self.lock.acquire(*args,**kwargs)
  if result:
   depth=getattr(self.local,'depth',0)
   if not depth:self.count+=1
   self.local.depth=depth+1
  return result
 def release(self):self.local.depth-=1;self.lock.release()
 def __enter__(self):self.acquire();return self
 def __exit__(self,*args):self.release()
 def __getattr__(self,name):return getattr(self.lock,name)
def movement(x):return struct.pack('>fffIBBHBii?i',float(x),0.,0.,0,0,0,0,0,0,0,False,0)
async def main():
 c=h.f.FriendsTests();await c.asyncSetUp();checks=[]
 try:
  peers=[]
  for n,identity in enumerate((c.alice,c.bob)):
   uid=seed(c,identity,'OwnMove'+str(n),False);p=await c.peer(identity);await p.roster();await p.enter_town(uid);peers.append(p)
  await c.server.periodics.close();s=c.app.playing[c.alice['id']];observer=c.app.playing[c.bob['id']];world=c.app.world
  original_handle=original_method('application.py','FriendsSession','handle',app_module)
  original_scope=original_method('dungeon_workers.py','DungeonWorkers','worker_scope',workers_module)
  probe=Counter(c.app.world_lock);c.app.world_lock=probe
  event=Event(0x202,kind=0x22b,payload=movement(77),performers=(0,));results={}
  for label,handle,scope in [('original',original_handle,original_scope),('proposal',FriendsSession.handle,DungeonWorkers.worker_scope)]:
   observer.mailbox.drain();s.mailbox.drain();probe.count=0
   with patch.object(FriendsSession,'handle',handle),patch.object(DungeonWorkers,'worker_scope',scope):
    replies=c.app._worker_call(s.handle,(event,),dict(request_sequence=501),time.perf_counter())
   admissions=probe.count;results[label]=(replies,observer.mailbox.drain(),s.account.get_location(),admissions)
  assert results['original'][:3]==results['proposal'][:3]
  assert results['proposal'][3]<results['original'][3],results
  checks.append(dict(case='valid_native_move',original_world_admissions=results['original'][3],proposal_world_admissions=results['proposal'][3],original_replies_peer_bytes_location_equal=True))
  for payload in(b'',bytes(3),movement(float('nan')),movement(float('inf'))):
   errors=[];before=s.account.get_location()
   for handle,scope in[(original_handle,original_scope),(FriendsSession.handle,DungeonWorkers.worker_scope)]:
    with patch.object(FriendsSession,'handle',handle),patch.object(DungeonWorkers,'worker_scope',scope):
     try:c.app._worker_call(s.handle,(Event(0x202,kind=0x22b,payload=payload,performers=(0,)),),dict(request_sequence=502),time.perf_counter())
     except Exception as error:errors.append((type(error).__name__,str(error)))
   assert len(errors)==2 and errors[0]==errors[1]and s.account.get_location()==before,errors
  checks.append('Malformed/nonfinite input rejection unchanged')
  for name,value in [('guild_agit',{}),('photo_zone',{}),('active_challenge',{})]:
   with patch.object(s,name,value,create=True):assert not DungeonWorkers.ordinary_town_move(s.handle,(event,))
  for mapping in(world.party_of,world.racing.queue,world.racing.offers,world.player_trades.by_session):
   assert s not in mapping;mapping[s]={}
   try:assert not DungeonWorkers.ordinary_town_move(s.handle,(event,))
   finally:del mapping[s]
  assert not DungeonWorkers.ordinary_town_move(s.handle,(Event(0x202,kind=0x48d),))
  checks.append('Party/racing queue+offer/trade/guild/photo/challenge/other-kind keep original route')
  world.racing.queue[s]={};before=s.account.get_location();observer.mailbox.drain()
  try:
   for handle in(original_handle,FriendsSession.handle):
    with patch.object(FriendsSession,'handle',handle):result=c.app._worker_call(s.handle,(event,),dict(request_sequence=503),time.perf_counter())
    assert s.account.get_location()==before and not observer.mailbox.drain()
  finally:del world.racing.queue[s]
  checks.append('Actual racing-waiting native consumer still suppresses movement')
 finally:await c.asyncTearDown()
 out=dict(passed=True,proposal_only=True,checks=checks,owned_runtime_removed=not c.root.exists(),connections=len(c.server.connections))
 (h.H/'town-move-lock-tests.json').write_text(json.dumps(out,indent=2),'utf8');print(json.dumps(out))
asyncio.run(main())
