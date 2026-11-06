from delivery_common import *
import asyncio,struct,sys,traceback
sys.dont_write_bytecode=True
parent=R/read(W/'publication/release-contract.json')['online']['parent']['path'];sys.path[:0]=[str(parent),str(R/'tools/pylibs'),str(R)]
from els_server.friends_bridge import Bridge,BridgeConfig
from els_server.protocol.protocol_codec import Event,encode_event,decode_event,encode_frame,decode_frame
from els_server.domain.town_travel import catalog as towns
h=load('ring_public_peer',R/'analysis/native-reuse-continuation-20261019-v1/protocol_helpers.py')
class Peer(h.Peer):
 async def send(self,kind,payload=b''):
  actors=(0,)if kind in(0x28,0x225,0x227,0x104)else()
  self.writer.write(encode_frame(encode_event(Event(0x202,kind=kind,payload=payload,performers=actors)),self.keys,spi=self.spi,sequence=self.outgoing));self.outgoing+=1;await self.writer.drain()
 async def until(self,kind):
  async with asyncio.timeout(20):
   for _ in range(500):
    e=decode_event(decode_frame(await h.read_wire(self.reader),self.keys,expected_sequence=self.incoming).plaintext);self.incoming+=1
    if e.kind==kind:return e
  raise AssertionError('Missing public response '+hex(kind))
 async def barrier(self):await self.send(0x48d);await self.until(0x48f)
def action(name):return remote('import runpy,sys;sys.argv=["qa_remote_worker.py",'+repr(name)+'];runpy.run_path('+repr(STAGE+'-qa/qa_remote_worker.py')+',run_name="__main__")')
async def main():
 cfg=read(W/'qa-credentials.private.json');peer=bridge=None;wires=[];report=dict(ok=False,public_TLS=True,own_controlled_fixture=True,natural_GUI=False)
 async def connect():
  nonlocal peer,bridge
  bridge=Bridge(BridgeConfig(**cfg['bridge']));peer=await Peer.open(bridge);await peer.roster()
  for kind,reply,payload in ((0x490,0x491,b''),(0x28,0x29,struct.pack('>Q',cfg['uid'])),(0x6e9,0x6ea,b''),(0x5bf,0x5c0,bytes(8)),(0x32,0x33,b''),(0x225,0x226,struct.pack('>iB',20000,0)),(0x227,0x228,struct.pack('>fffBH',*towns()['towns']['20000']['xyz'],0,0))):
   await peer.send(kind,payload);ack=await peer.until(reply)
   if kind in(0x225,0x227):assert ack.payload[:4]==bytes(4)
  await peer.barrier()
 async def close():
  nonlocal peer,bridge
  if peer:await peer.close();peer=None
  if bridge:await bridge.close();bridge=None
 async def request(kind,reply,payload=b''):
  await peer.send(kind,payload);ack=await peer.until(reply);await peer.barrier();return ack
 async def snapshot():return await asyncio.to_thread(action,'snapshot')
 def projection(rows):return {i['uid']:i for i in rows}
 async def move(source,destination,expected,label):
  intent=W/('public-wear-intent-'+label+'.json');assert not intent.exists();save(intent,dict(source=source,destination=destination,possible_mutation=True))
  ack=await request(0x104,0x105,struct.pack('>BiBiB',*source,*destination,0));assert ack.payload[-4:]==bytes(4)and struct.unpack_from('>I',ack.payload)[0]==3,(label,ack.payload[-4:].hex())
  wires.append(dict(label=label,wire_hex=ack.payload.hex(),expected=expected));save(W/'public-wires.private.json',wires)
 def row(item,group,slot):return dict(uid=item['uid'],template=item['template'],count=item['count'],group=group,slot=slot)
 def empty(group,slot):return dict(uid=0,template=0,count=0,group=group,slot=slot)
 try:
  await connect();before=await snapshot();offers=before['fixture']['offers'];ice=next(i for i in before['items']if i['uid']==before['fixture']['ice']['uid'])
  assert ice['group']==9 and ice['slot']==49 and not any(i['group']==27 for i in before['items'])
  await request(0x80d,0x80e,struct.pack('>i',1))
  assert not(W/'public-purchase-intent.json').exists();save(W/'public-purchase-intent.json',dict(offers=offers,possible_mutation=True))
  ack=await request(0x80f,0x810,struct.pack('>I',len(offers))+b''.join(struct.pack('>IH',r['sku'],1)for r in offers));assert ack.payload[:4]==bytes(4)
  bought=await snapshot();assert bought['ed']==before['ed']-sum(r['price']for r in offers)==100
  rings={t:next(i for i in bought['items']if i['template']==t)for t in(200700,270974,270975,270976,270977)}
  slots=sorted(i['slot']for i in bought['items']if i['group']==7);assert slots==list(range(len(slots)))
  for t,item in rings.items():
   source=(item['group'],item['slot']);assert source[0]==7
   await move(source,(9,49),[empty(*source),row(item,9,49),row(ice,27,0)],str(t)+'-wear')
   await move((27,0),(9,49),[empty(27,0),row(ice,9,49),row(item,*source)],str(t)+'-return')
  item=rings[270977];source=(7,item['slot'])
  await move(source,(9,49),[empty(*source),row(item,9,49),row(ice,27,0)],'cold-wear')
  held=await snapshot();assert projection(held['items'])[item['uid']]['group']==9 and projection(held['items'])[ice['uid']]['group']==27
  await close();await connect();cold=await snapshot();assert cold['items']==held['items']and cold['ed']==100
  await move((27,0),(9,49),[empty(27,0),row(ice,9,49),row(item,*source)],'cold-return')
  final=await snapshot();assert final['items']==bought['items']and final['ed']==100 and final['receipt_shapes']==[3]*12
  report.update(ok=True,ordinary_rings=list(rings),bidirectional_swaps=5,wear_ACKs=12,all_ACK_rows=3,ED_delta=-sum(r['price']for r in offers),cold_authenticated_equipped_restore=True,UIDs_and_full_instances_preserved=True,receipt_shapes=[3]*12,own_account_id=cfg['account_id'],native_decoder_pending=True)
 except BaseException as e:report.update(error=repr(e),traceback=traceback.format_exc());raise
 finally:
  await close();save(W/'public-acceptance.json',report)
 print(json.dumps(report))
if __name__=='__main__':asyncio.run(main())
