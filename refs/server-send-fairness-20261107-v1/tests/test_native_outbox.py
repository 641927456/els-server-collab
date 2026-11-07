import asyncio,dataclasses,importlib.util,struct,sys,unittest
from pathlib import Path
H=Path(__file__).resolve().parent;A=H.parent
from hypothesis import given,settings,strategies as st
from hypothesis.database import DirectoryBasedExampleDatabase
p=A/'source/els_server/native_outbox.py'
spec=importlib.util.spec_from_file_location('tested_native_outbox',p);m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
@dataclasses.dataclass(frozen=True)
class Notice:
 kind:int
 payload:bytes
 event_id:int=0x201
 performers:tuple=()
def move(uid,value):return Notice(0x22e,struct.pack('>QI',uid,value))
def barrier(n):return Notice(0x22a,struct.pack('>I',n))
def observed(events):
 state={};boundaries=[]
 for e in events:
  if e.kind==0x22e:uid,value=struct.unpack('>QI',e.payload);state[uid]=value
  else:boundaries.append((e.payload,dict(state)))
 return boundaries,state
events=st.lists(st.one_of(st.tuples(st.integers(1001,1006),st.integers(0,10000)).map(lambda p:move(*p)),st.integers(0,10000).map(barrier)),max_size=120)

class CoalescingProperties(unittest.TestCase):
 @settings(max_examples=150,deadline=None,database=None)
 @given(st.binary(max_size=2048),st.lists(st.integers(0,2**64-1),max_size=20))
 def test_estimate_matches_actual_native_encoder(self,payload,performers):
  import json
  base=A/'runtime-parent'
  name='measured_native_codec'
  if name not in sys.modules:
   spec=importlib.util.spec_from_file_location(name,base/'els_server/protocol/protocol_codec.py')
   codec=importlib.util.module_from_spec(spec);sys.modules[name]=codec;spec.loader.exec_module(codec)
  codec=sys.modules[name];event=codec.Event(0x201,kind=0x22e,payload=payload,performers=tuple(performers))
  self.assertEqual(m.wire_size(event),len(codec.encode_frame(codec.encode_event(event),codec.BOOTSTRAP_KEYS,iv=bytes(8))))
 @settings(max_examples=300,deadline=None,database=None)
 @given(events,st.integers(0,120))
 def test_state_at_every_barrier_and_batch_partition(self,values,split):
  first,_=m.TownBatch().merged(values)
  self.assertEqual(observed(first.messages),observed(values))
  self.assertLessEqual(len(first.messages),len(values))
  second,_=m.TownBatch().merged(values[:split]);second,_=second.merged(values[split:])
  self.assertEqual(second.messages,first.messages)
  canonical,_=m.TownBatch().merged(first.messages)
  self.assertEqual(canonical.messages,first.messages)

class QueueTests(unittest.IsolatedAsyncioTestCase):
 async def test_rosters_share_reliable_bytes_and_only_positions_use_short_lane(self):
  class Budget:
   chunk_size=4096
   def __init__(self):self.calls=[]
   async def wait(self,size,**kw):self.calls.append((size,kw['transient']))
  budget=Budget();written=[]
  async def send(messages,**options):written.append(tuple(messages))
  out=m.NativeOutbox(send,budget,1,self.fail,{})
  groups=[(barrier(1),),(move(1001,1),),(barrier(2),move(1001,2))]
  for values in groups:
   await out.submit(values,{},transient=True,context=1)
   while out.task is not None:await asyncio.sleep(0)
  self.assertEqual([v[1]for v in budget.calls],[False,True,False])
  self.assertEqual(written,groups);await out.close()
 async def test_latest_unsent_move_and_general_barrier(self):
  class Budget:
   chunk_size=4096
   def __init__(self):self.waiting=asyncio.Event();self.ready=asyncio.Event()
   async def wait(self,size,**kw):self.waiting.set();await self.ready.wait()
  budget=Budget();written=[];errors=[];metrics={}
  async def send(messages,**options):written.append(tuple(messages))
  out=m.NativeOutbox(send,budget,1,errors.append,metrics)
  await out.submit((move(1001,1),),{},transient=True,context=1);await budget.waiting.wait()
  await out.submit((move(1001,2),),{},transient=True,context=1)
  general=asyncio.create_task(out.submit((Notice(0xae,b'ack'),),{}));await asyncio.sleep(0)
  await out.submit((barrier(1),move(1001,3)),{},transient=True,context=1)
  budget.ready.set();await general
  while out.task is not None:await asyncio.sleep(0)
  self.assertEqual(written,[(move(1001,2),),(Notice(0xae,b'ack'),),(barrier(1),move(1001,3))])
  self.assertFalse(errors);self.assertEqual(metrics['outbound_pending_bytes'],0);await out.close()
 async def test_context_change_does_not_replace_old_scene(self):
  written=[];gate=asyncio.Event();started=asyncio.Event()
  class Budget:
   chunk_size=4096
   async def wait(self,n,**kw):started.set();await gate.wait()
  async def send(values,**kw):written.append(tuple(values))
  out=m.NativeOutbox(send,Budget(),1,self.fail,{})
  await out.submit((move(1001,1),),{},transient=True,context='old');await started.wait()
  await out.submit((move(1001,2),),{},transient=True,context='new')
  gate.set()
  while out.task is not None:await asyncio.sleep(0)
  self.assertEqual(written,[(move(1001,1),),(move(1001,2),)]);await out.close()
 async def test_timeout_and_close_release_bytes(self):
  errors=[];metrics={};started=asyncio.Event()
  class Budget:
   chunk_size=4096
   async def wait(self,n,**kw):started.set();await asyncio.Event().wait()
  async def send(*a,**kw):self.fail('No credit available')
  out=m.NativeOutbox(send,Budget(),.02,errors.append,metrics)
  await out.submit((move(1001,1),),{},transient=True,context=1)
  await started.wait()
  while out.task is not None:await asyncio.sleep(.005)
  self.assertIsInstance(errors[0],TimeoutError);self.assertEqual(metrics['outbound_pending_bytes'],0)
  with self.assertRaises(TimeoutError):await out.submit((move(1001,2),),{},transient=True,context=1)
  await out.close()
 async def test_explicit_queue_bound(self):
  gate=asyncio.Event();entered=asyncio.Event();metrics={}
  class Budget:
   chunk_size=4096
   async def wait(self,n,**kw):entered.set();await gate.wait()
  async def send(*a,**kw):pass
  out=m.NativeOutbox(send,Budget(),1,self.fail,metrics);out.group_limit=1
  await out.submit((move(1001,1),),{},transient=True,context=1);await entered.wait()
  with self.assertRaises(BufferError):await out.submit((Notice(0xae,b'ack'),),{})
  await out.close();self.assertEqual(metrics['outbound_pending_bytes'],0)
if __name__=='__main__':unittest.main()
