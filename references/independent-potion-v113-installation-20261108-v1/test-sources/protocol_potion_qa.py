"""Pinned TLS medicine requests for a single enrolled owned QA role."""
from pathlib import Path
import asyncio,json,struct,sys,time
W=Path(__file__).resolve().parent
plan=json.loads((W/'delivery-plan.json').read_bytes());D=Path(plan['build_path']).parent
R=Path(json.loads((D/'built-selection-verification.json').read_bytes())['selected_root'])
sys.path[:0]=[str(R),str(R/'tools/pylibs')]
from els_server.friends_bridge import Bridge,BridgeConfig
from els_server.protocol.protocol_codec import BOOTSTRAP_KEYS,Event,encode_event,encode_frame,decode_frame,decode_event,read_welcome

class Peer:
 async def open(self,bridge):
  self.reader,self.writer=await bridge.remote();self.spi,self.keys=read_welcome(decode_event(decode_frame(await self.wire(),BOOTSTRAP_KEYS).plaintext));self.outgoing=1;self.incoming=2
 async def wire(self):
  async with asyncio.timeout(15):
   head=await self.reader.readexactly(8);return head+await self.reader.readexactly(struct.unpack_from('<I',head)[0]-8)
 async def send(self,kind,payload=b''):
  if kind==0x5bf and not payload:payload=bytes(8)
  self.writer.write(encode_frame(encode_event(Event(0x202,kind=kind,payload=payload,performers=(0,))),self.keys,spi=self.spi,sequence=self.outgoing));self.outgoing+=1;await self.writer.drain()
 async def until(self,kind):
  async with asyncio.timeout(30):
   for _ in range(500):
    event=decode_event(decode_frame(await self.wire(),self.keys,expected_sequence=self.incoming).plaintext);self.incoming+=1
    if event.kind==kind:return event
  raise AssertionError(hex(kind))
 async def close(self):
  import ssl
  self.writer.close()
  try:await self.writer.wait_closed()
  except ssl.SSLError as error:
   if error.reason!='APPLICATION_DATA_AFTER_CLOSE_NOTIFY':raise

async def qualify(value):
 bridge=Bridge(BridgeConfig(**value['bridge']));peer=Peer();began=time.monotonic()
 try:
  await peer.open(bridge)
  for req,ack in ((0x1a,0x1b),(0x1e,0x19c),(0x35,0x36),(0x1ef,0x1f0),(0x39,0x3a),(0x485,0x488)):
   await peer.send(req);await peer.until(ack)
  for req,ack,payload in ((0x490,0x491,b''),(0x28,0x29,struct.pack('>Q',value['uid'])),(0x6e9,0x6ea,b''),(0x5bf,0x5c0,b''),(0x32,0x33,b''),(0x225,0x226,struct.pack('>iB',20000,0)),(0x227,0x228,struct.pack('>fffBH',1.,2.,3.,0,0))):
   await peer.send(req,payload);await peer.until(ack)
  await peer.send(0x7d4,struct.pack('>ii',1,30072));request=(await peer.until(0x7d5)).payload
  assert request[:4]==bytes(4),('ordinary dungeon request',request.hex())
  # Existing same-build original entry DTO; authenticated 7D4 selects the map.
  await peer.send(0x382,bytes.fromhex('eefc726aad751f003e6b6d2e0c4d36e2923600000010332b6d21282a5c1774790f0f3a4c7947'))
  answer=(await peer.until(0x383)).payload;assert answer[:4]==bytes(4),('ordinary dungeon admission',answer.hex())
  await peer.until(0x14a)
  await peer.send(0x91,struct.pack('>ii',100,0));await peer.until(0x92);await peer.until(0xb2)
  await peer.send(0xb3,bytes(9));await peer.until(0xb4);await peer.until(0xbd)
  first_sequence=peer.outgoing;started=time.perf_counter();await peer.send(0x113,bytes(5))
  ack=await peer.until(0x114);assert struct.unpack_from('>i',ack.payload)[0]==0,ack.payload.hex()
  effect=await peer.until(0x115);assert struct.unpack_from('>Qi',effect.payload)==(value['uid'],130165)
  elapsed=(time.perf_counter()-started)*1000
  await peer.send(0x113,bytes(5));refused=await peer.until(0x114);assert struct.unpack_from('>i',refused.payload)[0]==1369
  await peer.send(0x67,struct.pack('>i',0x72)+bytes(96));await peer.until(0x68)
  return dict(ok=True,certificate_pinned=True,ordinary_static_dungeon=30072,potion_template=130165,potion_sequence=first_sequence,cooldown_sequence=first_sequence+1,ack_and_effect_verified=True,cooldown_result=1369,exit_ack_verified=True,roundtrip_ms=elapsed,seconds=time.monotonic()-began,natural_GUI=False,natural_battle=False)
 finally:
  if hasattr(peer,'writer'):await peer.close()
  await bridge.close()

if __name__=='__main__':
 values=json.loads(Path(sys.argv[1]).read_bytes());assert len(values)==1
 print(json.dumps(asyncio.run(qualify(values[0]))))
