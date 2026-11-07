"""Link original producer counter schedules to the unchanged authenticated inbox."""
import asyncio,json,sys
from pathlib import Path
from types import SimpleNamespace
R=Path('G:/els');H=Path(__file__).resolve().parent
sys.path[:0]=[str(R/'releases/online/native-online-disconnect-repair-20261107-v1'),str(R/'tools/pylibs')]
from els_server.native_inbox import NativeInbox
from els_server.protocol.protocol_codec import BOOTSTRAP_KEYS,ProtocolError,Event,encode_event,encode_frame

async def check(values):
 q=asyncio.Queue();metrics={k:0 for k in('requests','town_moves_coalesced','auxiliary_coalesced')}
 for i,secure in enumerate(values,1):
  # Different business events, both with valid MAC, like two concurrent sends.
  e=Event(0x202,kind=(0x38e,0xff20)[i%2],payload=bytes(9),performers=(0,))
  q.put_nowait(encode_frame(encode_event(e),BOOTSTRAP_KEYS,spi=54723,sequence=i,secure_sequence=secure))
 inbox=NativeInbox(q.get,BOOTSTRAP_KEYS,SimpleNamespace(client_build='dx11_260923',role='game',phase='town_ready'),metrics)
 try:
  first=await inbox.get();assert first.sequence==1
  try:
   async with asyncio.timeout(2):second=await inbox.get()
  except ProtocolError as e:return {'accepted':1,'error':str(e)}
  assert second.sequence==2;return {'accepted':2,'error':None}
 finally:await inbox.close()

async def main():
 native=json.loads((H/'native-send-race.json').read_text())
 baseline=await check(native['concurrent_reads']);fixed=await check(native['serialized_reads'])
 assert baseline['accepted']==1 and 'previous=1039, received=1039'in baseline['error']
 assert fixed=={'accepted':2,'error':None}
 return dict(ok=True,authenticated_MAC_frames=True,unchanged_server_guard=True,controlled_original_native_schedule=True,
             baseline=baseline,serialized=fixed,natural_game=False,production_modified=False)
if __name__=='__main__':
 result=asyncio.run(main());(H/'sequence-inbox.json').write_text(json.dumps(result,indent=2)+'\n','utf8');print(json.dumps(result))
