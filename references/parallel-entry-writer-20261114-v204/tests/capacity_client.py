"""Twenty owned real TLS actors: actual admission, emitted HP, issued ED, doors."""
from pathlib import Path
from collections import defaultdict,deque,Counter
import argparse,asyncio,ast,hashlib,importlib.util,json,math,os,sqlite3,ssl,struct,sys,time,traceback,uuid
H=Path(__file__).resolve().parent;ROOT=H.parents[1];R=ROOT/'analysis/publisher-capacity-20261114-v204/runtime/combined'
sys.path[:0]=[str(R),str(R/'tools')];import ctypes
engine=ctypes.WinDLL(str(R/'python/sqlite3.dll'));assert sqlite3.sqlite_version=='3.54.1'and not sys._is_gil_enabled()
from els_server.friends_bridge import Bridge,BridgeConfig
from els_server.protocol.protocol_codec import BOOTSTRAP_KEYS,Event,read_welcome,encode_event,encode_frame,decode_event,decode_frame
from els_server.domain.dungeon_routes import DungeonRun
from els_server.domain.drop_pickup import GROUND_ED
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
probe=load('owned_capacity_native_gate',ROOT/'analysis/glass-door-20261104-v1/repair-v3/gate_probe.py')
ground=load('owned_capacity_ground',ROOT/'tests/test_ground_loot.py')
tree=ast.parse((ROOT/'analysis/dungeon-live-latency-20261105-v1/live_trial.py').read_bytes())
for node in tree.body:
 if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))and node.name in('admit','emitted_npc'):exec(compile(ast.Module(body=[node],type_ignores=[]),'qualified-admission-and-emitted-HP','exec'),globals())
parser=argparse.ArgumentParser();parser.add_argument('--actors',type=int,default=20);parser.add_argument('--seconds',type=int,default=1800);parser.add_argument('--offset',type=int,default=0);parser.add_argument('--phase',default='steady20');args=parser.parse_args()
W=H/args.phase;W.mkdir();rows=json.loads((H/'credentials.private.json').read_bytes())[args.offset:args.offset+args.actors];assert len(rows)==args.actors
samples=defaultdict(list);counts=Counter();coins=Counter();lag=[];active=set();peak=0;stop=False;started=None;started_epoch=None;last=0;ready=asyncio.Event();ready_count=0
REPLIES={0xad:0xae,0xd0:0xd2,0xb3:0xbd,0xb8:0xb9,0xbb:0xbc,0x227:0x228,0x28:0x29,0x91:0xb2,0x485:0x488}
def save(name,d):
 p=W/name;t=p.with_suffix('.next');t.write_text(json.dumps(d,indent=2)+'\n','utf8');os.replace(t,p)
def metric(v):
 v=sorted(v)
 return dict(n=len(v),p50_ms=v[len(v)//2],p95_ms=v[math.ceil(.95*len(v))-1],p99_ms=v[math.ceil(.99*len(v))-1],max_ms=v[-1])if v else None
async def read_wire(reader):
 h=await reader.readexactly(8);length=struct.unpack_from('<I',h)[0];assert 40<=length<=1024*1024
 return h+await reader.readexactly(length-8)
class Peer:
 @classmethod
 async def open(cls,b):
  self=cls();self.bridge=b;self.reader,self.writer=await b.remote()
  self.spi,self.keys=read_welcome(decode_event(decode_frame(await read_wire(self.reader),BOOTSTRAP_KEYS).plaintext));self.incoming=2;self.outgoing=1;self.pending=asyncio.Queue(2048);self.events=deque(maxlen=512);self.measuring={};self.last_clock=None
  async def receive():
   try:
    while True:
     f=decode_frame(await read_wire(self.reader),self.keys,expected_sequence=self.incoming);self.incoming+=1;e=decode_event(f.plaintext)
     self.events.append(e)
     if e.kind==0x9c:
      now=time.perf_counter()
      if self.last_clock is not None:samples['dungeon_clock_interval'].append((now-self.last_clock)*1000)
      self.last_clock=now
     if e.kind in self.measuring:
      k,t=self.measuring.pop(e.kind);samples[hex(k)].append((time.perf_counter()-t)*1000)
     self.pending.put_nowait(e)
   except Exception as e:self.pending.put_nowait(e)
  self.receiving=asyncio.create_task(receive());return self
 async def send(self,kind,payload=b'',event_id=0x202):
  if kind in REPLIES:self.measuring[REPLIES[kind]]=(kind,time.perf_counter())
  if kind==0x5bf and not payload:payload=bytes(8)
  self.writer.write(encode_frame(encode_event(Event(event_id,kind=kind,payload=payload,performers=(0,))),self.keys,spi=self.spi,sequence=self.outgoing));self.outgoing+=1;await self.writer.drain()
 async def until(self,kind):
  async with asyncio.timeout(8):
   while True:
    e=await self.pending.get()
    if isinstance(e,Exception):raise e
    if e.kind==kind:return e
 async def roster(self):
  for q,a in((0x1a,0x1b),(0x1e,0x19c),(0x35,0x36),(0x1ef,0x1f0),(0x39,0x3a),(0x485,0x488)):await self.send(q);await self.until(a)
 async def enter_town(self,uid,town=20000):
  for q,a,p in((0x490,0x491,b''),(0x28,0x29,struct.pack('>Q',uid)),(0x6e9,0x6ea,b''),(0x5bf,0x5c0,bytes(8)),(0x32,0x33,b''),(0x225,0x226,struct.pack('>iB',town,0)),(0x227,0x228,struct.pack('>fffBH',1.,2.,3.,0,0))):
   await self.send(q,p);e=await self.until(a)
   if q!=0x490:assert e.payload[:4]==bytes(4),(hex(q),e.payload[:8].hex())
 async def close(self):
  self.receiving.cancel();await asyncio.gather(self.receiving,return_exceptions=True);self.writer.close()
  try:await self.writer.wait_closed()
  except ssl.SSLError as e:
   if e.reason!='APPLICATION_DATA_AFTER_CLOSE_NOTIFY':raise
  await self.bridge.close()
async def enter(row):
 global peak
 b=Bridge(BridgeConfig(**row['bridge']));p=None
 try:
  p=await Peer.open(b);active.add(row['account_id']);peak=max(peak,len(active));await p.roster();stage=await admit(p,row['uid'],34710)
  run=DungeonRun(34710,str(uuid.uuid4()));npcs=[emitted_npc(n,stage)for n in run.current['npcs']]
  return p,npcs
 except BaseException:
  active.discard(row['account_id'])
  if p:await p.close()
  else:await b.close()
  raise
async def clear_room(row,p,npcs,index):
 start=time.monotonic()
 for n,npc in enumerate(npcs):
  intended=start+n*2.;await asyncio.sleep(max(0,intended-time.monotonic()));lag.append(max(0,time.monotonic()-intended)*1000)
  await p.send(0xad,probe.accepted_combat(npc,row['uid']));ack=await p.until(0xae);assert ack.payload==bytes(4),ack.payload.hex();counts['deaths']+=1
  while True:
   e=await p.until(0xcf)
   if struct.unpack_from('>i',e.payload,4)[0]in GROUND_ED:break
  fields=struct.unpack('>Iii?fIQb3f3i',e.payload);template,drop_id=fields[1:3]
  req=ground.request(template,drop_id,player_xyz=fields[8:11],drop_xyz=fields[8:11]);await p.send(0xd0,req.payload)
  ack=await p.until(0xd1);assert ack.payload==bytes(4);reward=struct.unpack('>Qiib?QIQiib?H',(await p.until(0xd2)).payload)
  assert reward[1:3]==(template,drop_id)and reward[7]==row['uid'];coins[str(row['uid'])]+=reward[8]+reward[9];counts['fresh_pickups']+=1
 if not any(e.kind==0xb7 and e.payload==b'\1'for e in p.events):assert(await p.until(0xb7)).payload==b'\1'
 begin=time.perf_counter();await p.send(0xb8,b'\1');assert(await p.until(0xb9)).payload==bytes(4);assert(await p.until(0xba)).payload==b'\1'
 await p.send(0xbb,b'\1');assert(await p.until(0xbc)).payload==bytes(4);assert(await p.until(0xbd)).payload[:1]==b'\1'
 samples['door_B8_to_BD'].append((time.perf_counter()-begin)*1000);counts['rooms']+=1
async def actor(row,index):
 global ready_count,started,started_epoch
 p=None
 try:
  await asyncio.sleep(index*.15)
  p,npcs=await enter(row);ready_count+=1
  if ready_count==len(rows):started=time.monotonic();started_epoch=time.time();ready.set()
  await ready.wait()
  while not stop:
   await clear_room(row,p,npcs,index);await p.close();p=None;active.discard(row['account_id'])
   if time.monotonic()-started>=args.seconds:break
   p,npcs=await enter(row);counts['reconnections']+=1
 finally:
  if p:await p.close()
  active.discard(row['account_id'])
async def main():
 global stop
 out=dict(ok=False,actors=len(rows),requested_steady_seconds=args.seconds,public_TLS=True,native_GUI=False,normal_admission=True,forced_server_room=False,actual_original_HP_and_issued_drop=True)
 tasks=[asyncio.create_task(actor(r,i))for i,r in enumerate(rows)];begin=time.monotonic()
 try:
  while any(not t.done()for t in tasks):
   await asyncio.sleep(2)
   failed=[t for t in tasks if t.done()and not t.cancelled()and t.exception()is not None]
   if failed:raise failed[0].exception()
   if(H/'cancel-capacity').exists():raise RuntimeError('Explicit owned workload cancellation')
   elapsed=0 if started is None else time.monotonic()-started
   if started is None and time.monotonic()-begin>120:raise TimeoutError('Twenty normal admissions not completed')
   save('progress.json',dict(phase=args.phase,actors=len(rows),ready=ready_count,active_connections=len(active),peak_connections=peak,steady_seconds=elapsed,counts=counts,samples={k:metric(v)for k,v in samples.items()},generator_cpu_seconds=time.process_time(),workload_lag=metric(lag)))
   if elapsed>=args.seconds:stop=True
  await asyncio.gather(*tasks);out.update(ok=True,steady_seconds=time.monotonic()-started)
 except BaseException as e:out.update(error=repr(e),traceback=traceback.format_exc());raise
 finally:
  stop=True
  for t in tasks:
   if not t.done():t.cancel()
  await asyncio.gather(*tasks,return_exceptions=True)
  out.update(expected_game_authentications=len(rows)+counts['reconnections'],steady_started_epoch=started_epoch,completed_epoch=time.time(),wall_seconds=time.monotonic()-begin,counts=counts,expected_ED=dict(coins),peak_connections=peak,connections_drained=len(active)==0,samples={k:metric(v)for k,v in samples.items()},generator_workload_lag=metric(lag),source_runtime=str(R),GIL_enabled=sys._is_gil_enabled())
  save('result.json',out);save('samples.private.json',dict(samples));print(json.dumps(out),flush=True)
if __name__=='__main__':asyncio.run(main())
