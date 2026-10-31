from pathlib import Path
from contextlib import closing,ExitStack
from unittest.mock import patch
import asyncio,collections,hashlib,importlib.util,json,os,sqlite3,struct,sys,tempfile,unittest
H=Path(__file__).resolve().parent;R=Path(os.environ.get('ELS_COMMON_BOX_RUNTIME',H/'runtime'))
os.environ['ELS_OWNED_BOX_TEST_RUNTIME']=str(R)
fixture=Path(os.environ.get('ELS_COMMON_BOX_FIXTURE','G:/els/analysis/owned-box-opening-20261031-v1/source/references/owned-box-opening-20261031-v2/test_boxes.py'))
spec=importlib.util.spec_from_file_location('owned_fixture',fixture);base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
os.environ['TMP']=os.environ['TEMP']=str(H);tempfile.tempdir=str(H)
from els_server.game_data import client_data
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import load_items
from els_server.domain.inventory_items import VERIFIED_TEMPLATES
from els_server.protocol.protocol_codec import Event,encode_event
audit=json.loads((H/'audit.json').read_text(encoding='utf8'));ROWS=[]

def totals(items):
 result=collections.Counter()
 for i in items:result[i['template']]+=i['count']
 return result

class Common(base.Boxes):
 def setUp(self):
  super().setUp()
  self.s.enter_town=True;self.s.pending_map=self.s.active_map;self.s.dungeon_return_pending=False
  with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE location SET town=? WHERE uid=?',(self.s.active_map,self.uid))
  self.account.location=self.account.store.load()
 def grant(self,t,count=1):
  # Synthetic pre-existing inventory, only in the fixture's isolated database.
  # Production grant gates and typed source capabilities are unchanged.
  with closing(sqlite3.connect(self.path))as db,db:
   db.execute('BEGIN IMMEDIATE');items=load_items(db,self.uid)
   slot=next(n for n in range(1000)if not any(i['group']==4 and i['slot']==n for i in items))
   uid=db.execute('SELECT next_uid FROM inventory_sequence WHERE id=1').fetchone()[0]
   db.execute('UPDATE inventory_sequence SET next_uid=? WHERE id=1',(uid+1,))
   db.execute('INSERT INTO inventory_items VALUES (?,?,?,?,?,?,?)',(uid,self.uid,t,VERIFIED_TEMPLATES.get(t,client_data().item(t)['metadata']),count,4,slot))
   return next(i for i in load_items(db,self.uid)if i['uid']==uid)
 def send(self,box,choices=(),count=1,sequence=100):
  return self.s.handle(Event(0x202,performers=(0,),kind=0x196,payload=base.wire(box['uid'],choices,count)),sequence)
 def failed(self,box,choices=(),count=1,sequence=100):
  before=self.snapshot();answer=self.send(box,choices,count,sequence)
  self.assertNotEqual(struct.unpack_from('>i',base.ack(answer,0x197).payload)[0],0)
  self.assertEqual(self.snapshot(),before)
 def exercise(self,t,group,representative):
  box=self.grant(t);preview_event=Event(0x202,performers=(0,),kind=0x559,payload=struct.pack('>iIiBB',t,1,0,0,0))
  preview=self.s.handle(preview_event,90);raw=base.ack(preview,0x55a).payload
  self.assertEqual(struct.unpack_from('>i',raw)[0],0,('preview',t))
  selection,n=struct.unpack_from('>iI',raw,13);entries=[struct.unpack_from('>iii',raw,21+12*k)for k in range(n)]
  self.assertTrue(entries);choices=tuple(e[0]for e in entries[:selection])
  for index,count in enumerate((-1,2)):
   self.failed(box,choices,count,95+index)
  if representative:
   if selection:self.failed(box,(),sequence=97);self.failed(box,(2147483647,),sequence=98)
   else:self.failed(box,(2147483647,),sequence=98)
   # A failure after inventory construction must roll back the debit and grants.
   before=self.snapshot()
   module='els_server.storage.'+({'black_market_box_rules':'black_market_boxes'}.get(group,group))
   import importlib
   target=importlib.import_module(module)
   with ExitStack()as injected:
    mock=injected.enter_context(patch('els_server.protocol.protocol_codec.encode_event',side_effect=ValueError('controlled late codec failure')))
    if hasattr(target,'encode_event'):injected.enter_context(patch.object(target,'encode_event',mock))
    try:answer=self.send(box,choices,sequence=99)
    except ValueError:pass
    self.assertTrue(mock.called,'Fault must reach an encoder inside the transaction')
   self.assertEqual(self.snapshot(),before)
  before=self.items();foreign=self.items(self.other);balances=self.account.get_reward_balances()
  answer=self.send(box,choices);result=base.ack(answer,0x197).payload
  self.assertEqual(struct.unpack_from('>i',result)[0],0,('use',t))
  for e in answer:encode_event(e)
  after=self.items();self.assertFalse(any(i['uid']==box['uid']for i in after))
  reward_count=struct.unpack_from('>I',result,12)[0]
  rewards=collections.Counter(dict(struct.unpack_from('>ii',result,16+8*k)for k in range(reward_count)))
  delta=totals(after);delta.subtract(totals(before));delta[t]+=1;delta=+delta
  self.assertEqual(delta,rewards,('committed inventory vs displayed reward map',t))
  self.assertTrue(delta);self.assertEqual(self.items(self.other),foreign);self.assertEqual(self.account.get_reward_balances()['ed'],balances['ed'])
  saved=self.snapshot();self.send(box,choices);self.assertEqual(self.snapshot(),saved)
  cold=LocalAccount(LocalState(self.path,self.uid));cold.enable_characters();self.assertEqual(cold.get_inventory_snapshot()['items'],after)
  with closing(sqlite3.connect(self.path))as db:self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
  if representative:
   payloads=dict(template=t,preview=raw.hex(),inventory=base.ack(answer,0xad8).payload.hex(),result=result.hex())
   (H/'native-inputs').mkdir(exist_ok=True);(H/'native-inputs'/f'{t}.json').write_text(json.dumps(payloads),encoding='utf8')
   # Historical Count0 remains a single opening on a different owned item.
   second=self.grant(t);response=self.send(second,choices,count=0,sequence=101)
   self.assertEqual(struct.unpack_from('>i',base.ack(response,0x197).payload)[0],0)
  ROWS.append(dict(template=t,group=group,preview_entries=n,Count1=True,Count0=representative,reject_negative_and_bulk=True,late_encoder_atomic=representative,replay=True,cold=True,rewards=dict(delta)))

suite=unittest.TestSuite()
for group in audit['groups']:
 for i,row in enumerate(group['templates']):
  t=row['template'];name=f'test_{t}'
  def test(self,t=t,g=group['group'],representative=i==0):self.exercise(t,g,representative)
  setattr(Common,name,test)
  if len(sys.argv)==1 or str(t)in sys.argv[1:]:suite.addTest(Common(name))
if __name__=='__main__':
 result=unittest.TextTestRunner(verbosity=2).run(suite)
 out=dict(ok=result.wasSuccessful(),tests=result.testsRun,errors=[s for _,s in result.errors],failures=[s for _,s in result.failures],rows=ROWS,layer='Actual Application-owned LocalSession; controlled town/level99 class150; synthetic owned items in private G-drive SQLite',natural_GUI=False,installed=False)
 (H/('tests-all.json'if len(sys.argv)==1 else'tests-affected.json')).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps(dict(ok=out['ok'],tests=out['tests'],passed=len(ROWS))));sys.exit(not result.wasSuccessful())
