"""Correlate authenticated repeats without accepting them or exporting packets."""
from pathlib import Path
from types import SimpleNamespace
import asyncio,json,struct,sys
H=Path(__file__).resolve().parent;C=H/'candidate';R=Path('G:/els')
sys.dont_write_bytecode=True;sys.path[:0]=[str(C),str(R/'tools/pylibs')]
from els_server.native_inbox import NativeInbox
from els_server.protocol.protocol_codec import Event,ProtocolError,BOOTSTRAP_KEYS,encode_event,encode_frame

def frame(kind,outer,secure,iv,*,spi=54723):
 return encode_frame(encode_event(Event(0x202,kind=kind,performers=(0,),payload=bytes(9))),
     BOOTSTRAP_KEYS,sequence=outer,secure_sequence=secure,spi=spi,iv=bytes([iv])*8)

async def check(wires):
 q=asyncio.Queue();metrics={k:0 for k in('requests','town_moves_coalesced','auxiliary_coalesced')}
 for wire in wires:q.put_nowait(wire)
 inbox=NativeInbox(q.get,BOOTSTRAP_KEYS,SimpleNamespace(client_build='dx11_260923',role='game',phase='town_ready'),metrics)
 try:
  accepted=0
  try:
   async with asyncio.timeout(3):
    for _ in wires:await inbox.get();accepted+=1
  except ProtocolError as error:return dict(accepted=accepted,error=str(error))
  return dict(accepted=accepted,error=None)
 finally:await inbox.close()

async def main():
 original=frame(0x38e,1,1039,1);same=bytearray(original);struct.pack_into('<I',same,4,2)
 cases={
     'same_body':([original,bytes(same)],True,True),
     'different_business':([original,frame(0xff20,2,1039,2)],False,False),
     'same_plaintext_new_encryption':([original,frame(0x38e,2,1039,2)],False,True)}
 result={}
 for name,(wires,body_equal,plain_equal)in cases.items():
  out=await check(wires);assert out['accepted']==1
  detail=json.loads(out['error'].split('; correlation=',1)[1])
  assert detail['compared_adjacent']is True and detail['same_authenticated_body']is body_equal and detail['same_plaintext']is plain_equal
  assert not any(s in out['error']for s in('sha256','fingerprint','iv=','plaintext='))
  result[name]=detail
 assert await check([original,frame(0xff20,2,1040,2)])==dict(accepted=2,error=None)
 assert await check([frame(0x38e,1,0xffffffff,1),frame(0xff20,2,1,2)])==dict(accepted=2,error=None)
 for value in(0,1038):assert(await check([original,frame(0xff20,2,value,2)]))['accepted']==1
 tampered=bytearray(frame(0xff20,2,1040,2));tampered[-1]^=1
 bad=await check([original,bytes(tampered)])
 assert bad['error']=='Invalid authentication tag'and bad['accepted']==1
 return dict(ok=True,repeat_cases=result,anti_replay_unchanged=True,MAC_precedes_correlation=True,
     ordered_and_wrap_accepted=True,raw_packets_or_digests_emitted=False,production_modified=False)

if __name__=='__main__':
 result=asyncio.run(main());(H/'sequence-correlation.json').write_text(json.dumps(result,indent=2)+'\n','utf8');print(json.dumps(result))
