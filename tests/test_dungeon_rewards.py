"""Actual session lifecycle gates durable grants; replay/failure never duplicates."""
import json,sqlite3,struct,sys,tempfile
from pathlib import Path
from contextlib import closing
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from local_session import LocalAccount,LocalSession
from local_state import LocalState
from protocol_codec import Event
from dungeon_population import population
from dungeon_clear import reward_clear_notice
body=bytes.fromhex(json.loads((ROOT/'analysis/client-6c6b5180/20261013-160720/death-event-header.json').read_text(encoding='utf8'))[0]['payload'])
entry=bytes.fromhex('eefc726aad751f003e6b6d2e0c4d36e2923600000010332b6d21282a5c1774790f0f3a4c7947')
def death(n):
 b=bytearray(body);struct.pack_into('>i',b,0,n['key']);struct.pack_into('>f',b,46,n['hp']);return Event(0x202,performers=(0,),kind=0xad,payload=bytes(b))
bb=Event(0x202,kind=0xbb,payload=b'\0');b3=Event(0x202,kind=0xb3,payload=bytes(9))
def allocate(s):
 s.role='game';s.phase='town_ready'
 s.handle(Event(0x202,kind=0x7d4,payload=struct.pack('>ii',1,30000)))
 assert [e.kind for e in s.handle(Event(0x202,kind=0x382,payload=entry))]==[0x383,0x14a]
 s.handle(Event(0x202,kind=0x91,payload=struct.pack('>ii',100,0)));s.handle(b3)
def clear_stage(s,stage):
 p=population(stage)
 for n in p['npcs']:
  if n['active'] or n['key']==p['clear_key']:
   s.handle(death(n))
 return s.handle(bb)
with tempfile.TemporaryDirectory() as d:
 path=Path(d)/'state.sqlite3';a=LocalAccount(LocalState(path))
 args={'enter_town':True,'enter_dungeon':True,'client_build':'dx11_260923','npc_slot_test':True,'gate_test':True,'population_test':True,'clear_test':True,'reward_test':True}
 s=LocalSession(a,**args);allocate(s);run=s.reward_run_id
 assert run and s.handle(bb)==[] and a.get_reward_balances()=={'ed':0,'experience':0,'revision':0}
 for stage in range(2):
  assert [e.kind for e in clear_stage(s,stage)]==[0xbc,0xb2];s.handle(b3)
  assert a.get_reward_balances()['revision']==0
 s.handle(death(population(2)['npcs'][0]))
 # Failure after balance update, during receipt insert, must leave the run
 # unnotified and retryable, without granting any ED/experience.
 with closing(sqlite3.connect(path)) as db,db:db.execute("CREATE TRIGGER fail_reward BEFORE INSERT ON reward_receipts BEGIN SELECT RAISE(ABORT,'failure injected'); END")
 try:s.handle(bb)
 except sqlite3.IntegrityError:pass
 else:raise AssertionError('Grant failure ignored')
 assert not s.clear_notified and s.reward_run_id==run and a.get_reward_balances()['revision']==0
 with closing(sqlite3.connect(path)) as db,db:db.execute('DROP TRIGGER fail_reward')
 reply=s.handle(bb);assert [e.kind for e in reply]==[0xbc,0xc1]
 assert reply[1].payload==reward_clear_notice(120,50).payload
 assert a.get_reward_balances()=={'ed':120,'experience':50,'revision':1}
 assert [e.kind for e in s.handle(bb)]==[0xbc] and a.get_reward_balances()['revision']==1
 # Simulate a failure between durable commit and the in-memory sent flag.
 s.clear_notified=False;s.reward_receipt=None
 retry=s.handle(bb);assert retry[1].payload==reply[1].payload and s.reward_receipt['replayed']
 assert a.get_reward_balances()['revision']==1
 # Confirming the result exit must receive the native 111 response immediately.
 exit_request=Event(0x202,kind=0x110,payload=b'')
 exit_reply=s.handle(exit_request)
 assert len(exit_reply)==1 and exit_reply[0].kind==0x111 and exit_reply[0].payload==bytes(12)
 assert s.handle(exit_request)==exit_reply and s.phase=='dungeon_active'
 assert s.handle(Event(0x202,kind=0x110,payload=b'\0'))==[]
 reopened=LocalAccount(LocalState(path));assert reopened.get_reward_balances()==a.get_reward_balances()
 # Direct original C1 return restores the committed total before town ACK.
 returned=s.handle(Event(0x202,kind=0x225,payload=struct.pack('>i',20000)+b'\0'))
 assert [e.kind for e in returned]==[0xd9,0x226] and s.phase=='square_accepted'
 from local_messages import character_unit
 expected=character_unit(a.get_location(),True,a.get_skills(),a.get_reward_balances())
 assert returned[0].payload==expected+bytes(9) and a.get_reward_balances()['revision']==1
 allocate(s);assert s.reward_run_id!=run and not s.clear_notified
 assert s.handle(exit_request)==[]
 assert [e.kind for e in clear_stage(s,0)]==[0xbc,0xb2] and a.get_reward_balances()['revision']==1
 # Ordinary profiles cannot opt into grants or marker-payload persistence.
 for bad in [{},{'clear_test':True},{**args,'reward_probe':True}]:
  try:LocalSession(a,**{**bad,'reward_test':True})
  except ValueError:pass
  else:raise AssertionError('Invalid persistent reward profile')
print('PASS: original stage/Boss gates, transactional C1 grant, failure retry, once-only replay, fresh run UUID, saved account reload and diagnostic isolation.')
