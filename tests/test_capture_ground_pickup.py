"""Run the capture endpoint's real worker/framing/logging over a socket pair.

Only CLI startup is excluded; the session is preloaded with issued loot to avoid
requiring a graphical dungeon walkthrough for a logging-path regression.
"""
import ast,hashlib,json,secrets,socket,struct,sys,tempfile,threading,time
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from els_server.protocol.protocol_codec import *
from els_server.domain.local_session import SessionOrderError
from test_ground_loot import session,issue,request

source=ast.parse((ROOT/'capture_server.py').read_text(encoding='utf8'))
worker=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=='handle')
def read_wire(s):
 def exact(n):
  result=b''
  while len(result)<n:
   chunk=s.recv(n-len(result))
   assert chunk,'Connection closed before pickup response'
   result+=chunk
  return result
 header=exact(8);return header+exact(struct.unpack_from('<I',header)[0]-8)

with tempfile.TemporaryDirectory() as d:
 out=Path(d);business=session(out/'save.sqlite3')
 for template,drop_id,ed in ((127000,910001,10),(70040,910002,0),(77000,910003,0)):
  issue(business,template,drop_id,ed)
 flags=dict(enter_town=True,enter_dungeon=True,client_build='dx11_260923',
            npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,
            reward_probe=False,reward_test=True,item_test=True,drop_probe=True,
            drop_test=True,boss_gauge_test=False,shop_test=False,ice_test=False,
            generate_welcome=True,corrupt_welcome_mac=False,local_identity=True,
            until_stopped=True,native_clear_replay=False,label='pickup-regression')
 events=[];stop=threading.Event();row={'chunks':[]}
 env=dict(globals(),a=SimpleNamespace(**flags),out=out,captured_welcome=b'',
          followup=b'',local_account=business.account,started=time.monotonic(),
          running=lambda:not stop.is_set(),LocalSession=lambda *a,**k:business,
          log=lambda event,**values:events.append(dict(event=event,**values)))
 exec(compile(ast.Module(body=[worker],type_ignores=[]),'capture_server.py','exec'),env)
 server,client=socket.socketpair();client.settimeout(3)
 thread=threading.Thread(target=env['handle'],args=(server,row,1));thread.start()
 try:
  spi,keys=read_welcome(decode_event(decode_frame(read_wire(client),BOOTSTRAP_KEYS).plaintext))
  sequence=2
  cases=[(127000,910001,[0xd1,0xd2]),(70040,910002,[0xd1,0xd2]),
         (77000,910003,[0xd1,0xd2,0xd3]),(127000,910001,[0xd1])]
  for n,(template,drop_id,expected) in enumerate(cases,1):
   client.sendall(encode_frame(encode_event(request(template,drop_id)),keys,spi=spi,sequence=n))
   kinds=[]
   for _ in expected:
    kinds.append(decode_event(decode_frame(read_wire(client),keys,expected_sequence=sequence).plaintext).kind)
    sequence+=1
   assert kinds==expected,(kinds,expected)
  assert business.account.get_reward_balances()['ed']==10
  assert business.account.get_inventory_snapshot()['items'][0]['count']==1
 finally:
  client.close();stop.set();thread.join(5)
 assert not thread.is_alive()
 assert 'worker_error' not in row,row
 logs=[e for e in events if e['event'].startswith('local_world_pickup_')]
 assert len(logs)==4 and logs[0]['items']==logs[1]['items']==logs[3]['items']==[]
 assert logs[2]['items'][0]['template']==77000
print('PASS: real capture worker keeps encrypted connection alive across coin, food, inventory and duplicate pickups; receipts log safely.')
