from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import asyncio,collections,json,os,sqlite3,struct,sys,tempfile,time,unittest
HOME=Path(__file__).resolve().parent;R=Path(os.environ['ELS_OWNED_BOX_TEST_RUNTIME']);sys.path.insert(0,str(R))
os.environ['TMP']=os.environ['TEMP']=str(HOME)
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.storage.inventory_state import grant_items,load_items
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.domain.tenebros_capacity_flow import selected
from els_server.storage.fixed_cubes import open_cube
from els_server.domain.owned_reward_boxes import outputs_for,BOXES
ROWS=[]
def wire(uid,choices=(),count=1):
 return struct.pack('>QBBBI',uid,0,0,0,len(choices))+b''.join(struct.pack('>i',x)for x in choices)+struct.pack('>i',count)
def ack(events,kind):return next(e for e in events if e.kind==kind)
class Boxes(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='owned-box-');self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'game.sqlite3'
  self.root=LocalAccount(LocalState(self.path));self.root.enable_characters();self.uid=self.root.characters.create('BoxOwner',1,'box-owner')['uid']
  self.other=self.root.characters.create('BoxOther',5,'box-other')['uid'];self.account=self.root.for_character(self.uid)
  self.account.get_inventory_snapshot();self.root.for_character(self.other).get_inventory_snapshot()
  self.app=Application(ServerConfig(state_file=self.path));self.app.account=self.root
  self.addCleanup(self.app.executor.shutdown,wait=True)
  self.s=asyncio.run(self.app.session());self.s.account=self.account;self.s.role='game';self.s.phase='town_ready';self.s.active_map=20001;self.s.completed.update((0x28,0x225,0x227))
  self.career(150)
 def career(self,cls):
  from els_server.domain.character_rules import CLASSES
  from els_server.game_data import client_data
  meta=CLASSES[cls]
  with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE characters SET unit_type=?,unit_class=?,level=?,transcendence=?,master=0 WHERE uid=?',(client_data().unit(cls)['unitType'],cls,99,int(meta['stage']==3),self.uid))
 def items(self,uid=None):
  with closing(sqlite3.connect(self.path))as db:return load_items(db,self.uid if uid is None else uid)
 def snapshot(self):
  with closing(sqlite3.connect(self.path))as db:return tuple(db.iterdump())
 def grant(self,template,count=1):
  with closing(sqlite3.connect(self.path))as db,db:
   db.execute('BEGIN IMMEDIATE')
   if template==723618:
    # This is a retained owned reader; preserve its real closed grant gate.
    # Seed a synthetic pre-existing row only in this fixture's private save.
    items=load_items(db,self.uid);slot=next(n for n in range(1000)if not any(i['group']==4 and i['slot']==n for i in items))
    uid=db.execute('SELECT next_uid FROM inventory_sequence WHERE id=1').fetchone()[0]
    db.execute('UPDATE inventory_sequence SET next_uid=? WHERE id=1',(uid+1,))
    db.execute('INSERT INTO inventory_items VALUES (?,?,?,?,?,?,?)',(uid,self.uid,template,VERIFIED_TEMPLATES[template],count,4,slot))
    return next(i for i in load_items(db,self.uid)if i['uid']==uid)
   return grant_items(db,[dict(template=template,metadata=VERIFIED_TEMPLATES[template],group=TEMPLATE_BAG_GROUPS[template],quantity=count)],self.uid)[0]
 def use(self,box,op,choices=(),count=1):
  path,uid,account,prepare=selected(self.s)
  if box['template']in(109999,110850):
   from els_server.storage.promotion_reward_boxes import open_box
   return open_box(path,uid,box['template'],wire(box['uid'],choices,count),op,account_id=account,prepare=prepare)
  return open_cube(path,uid,box['template'],wire(box['uid'],choices,count),op,account_id=account,prepare=prepare)
 def reject(self,call):
  before=self.snapshot()
  with self.assertRaises(ValueError):call()
  self.assertEqual(self.snapshot(),before)
 def test_existing_five_single_count_through_actual_app_handler(self):
  for n,t in enumerate((109999,110850,300645,300646,300647)):
   with self.subTest(template=t):
    box=self.grant(t);before=self.items();balances=self.account.get_reward_balances();foreign=self.items(self.other)
    for count in(-1,2,99):self.reject(lambda count=count:self.use(box,f'bad-{t}-{count}',count=count))
    preview=Event(0x202,performers=(0,),kind=0x559,payload=struct.pack('>iIiBB',t,1,0,0,0))
    reply=self.s.handle(preview,100+n*3);self.assertEqual(struct.unpack_from('>i',ack(reply,0x55a).payload)[0],0)
    event=Event(0x202,performers=(0,),kind=0x196,payload=wire(box['uid']))
    reply=self.s.handle(event,101+n*3);self.assertEqual(struct.unpack_from('>i',ack(reply,0x197).payload)[0],0)
    for e in reply:encode_event(e)
    after=self.items();new=[i for i in after if i['uid']not in {v['uid']for v in before}]
    self.assertFalse(any(i['uid']==box['uid']for i in after));self.assertTrue(new)
    snapshot=self.snapshot();retry=self.s.handle(event,101+n*3);self.assertEqual(self.snapshot(),snapshot)
    self.assertEqual(struct.unpack_from('>I',ack(retry,0x197).payload,12)[0],0)
    self.assertEqual(self.items(self.other),foreign);self.assertEqual(self.account.get_reward_balances()['ed'],balances['ed'])
    cold=LocalAccount(LocalState(self.path,self.uid));cold.enable_characters();self.assertEqual(cold.get_inventory_snapshot()['items'],after)
    ROWS.append(dict(template=t,Count1=True,replay_no_increment=True,cold=True,outputs=len(new),layer='Actual Application-owned LocalSession with controlled town/character fixture'))
 def test_added_boxes_positive_preview_use_and_cold(self):
  for n,t in enumerate(sorted(BOXES)):
   with self.subTest(template=t):
    box=self.grant(t);outputs=outputs_for(t,self.account.character());choices=(outputs[0]['template'],)if t in(723687,723688)else()
    before=self.items();preview=Event(0x202,performers=(0,),kind=0x559,payload=struct.pack('>iIiBB',t,1,0,0,0))
    reply=self.s.handle(preview,300+n*3);self.assertEqual(struct.unpack_from('>i',ack(reply,0x55a).payload)[0],0)
    self.assertEqual(struct.unpack_from('>I',ack(reply,0x55a).payload,17)[0],len(outputs))
    event=Event(0x202,performers=(0,),kind=0x196,payload=wire(box['uid'],choices))
    reply=self.s.handle(event,301+n*3);self.assertEqual(struct.unpack_from('>i',ack(reply,0x197).payload)[0],0)
    for e in reply:encode_event(e)
    after=self.items();self.assertFalse(any(i['uid']==box['uid']for i in after))
    new=[i for i in after if i['uid']not in {v['uid']for v in before}]
    self.assertEqual(sum(i['count']for i in new),1 if choices else sum(o['quantity']for o in outputs))
    if t in(135666,135871):
     days=7 if t==135666 else 3
     self.assertTrue(all(abs(i['expires_at']-(int(time.time())+days*86400))<3 for i in new))
    snapshot=self.snapshot();retry=self.s.handle(event,301+n*3);self.assertEqual(self.snapshot(),snapshot)
    self.assertEqual(struct.unpack_from('>I',ack(retry,0x197).payload,12)[0],0)
    cold=LocalAccount(LocalState(self.path,self.uid));cold.enable_characters();self.assertEqual(cold.get_inventory_snapshot()['items'],after)
    ROWS.append(dict(template=t,Count1=True,replay_no_increment=True,cold=True,outputs=len(new),preview_choices=len(outputs)))
 def test_added_boxes_roll_back_capacity_late_encoding_and_wrong_choice(self):
  box=self.grant(117542)
  fashion=self.grant(135666)
  from els_server.storage.bag_capacity import allowances
  with closing(sqlite3.connect(self.path))as db:limits=allowances(db,self.uid)
  limits[27]=5+max((i['slot']+1 for i in self.items()if i['group']==27),default=0)
  with patch('els_server.storage.bag_capacity.allowances',return_value=limits):
   self.reject(lambda:self.use(fashion,'five-free-for-six'))
  with patch('els_server.protocol.protocol_codec.encode_event',side_effect=ValueError('late-codec')):
   self.reject(lambda:self.use(box,'late-codec'))
  force=self.grant(723687)
  self.reject(lambda:self.use(force,'foreign-class-choice',(390190,)))
  self.reject(lambda:self.use(force,'no-choice'))
  self.reject(lambda:self.use(force,'bulk',(390188,),count=2))
  from els_server.storage.item_locks import assign
  with closing(sqlite3.connect(self.path))as db,db:db.execute('BEGIN IMMEDIATE');assign(db,self.uid,force['uid'],int(time.time())+300)
  self.reject(lambda:self.use(force,'locked',(390188,)))
 def test_class_matrix_and_unqualified_rejection(self):
  from els_server.domain.owned_reward_boxes import catalog
  from els_server.domain.character_rules import CLASSES
  for box in catalog()['boxes']:
   if box['template']in(723687,723688):
    self.assertEqual(len(box['class_outputs']),60)
    self.assertEqual({len(r)for r in box['class_outputs'].values()},{2 if box['template']==723687 else 4})
  self.career(1);box=self.grant(723687);self.reject(lambda:self.use(box,'base-rejected',(390188,)))
  for t in(109999,110850):
   box=self.grant(t);self.reject(lambda:self.use(box,f'career-base-{t}'))
  self.career(177)
  self.assertEqual(len(outputs_for(135666,self.account.character())),12)
  self.assertEqual(len(outputs_for(135871,self.account.character())),10)
 def test_artifact_fixed_lines_separate_rings_empty_spirit_cold_and_rollback(self):
  from els_server.domain.acquisition_policy import can_acquire
  self.assertFalse(can_acquire(723618))
  box=self.grant(723618);before=self.items();answer=self.use(box,'artifact-fixed')
  self.assertEqual(struct.unpack_from('>i',ack(answer,0x197).payload)[0],0)
  after=self.items();new=[i for i in after if i['uid']not in {v['uid']for v in before}]
  self.assertEqual(len(new),5);self.assertEqual(collections.Counter(i['template']for i in new),{168600:1,168601:1,168602:1,168603:2})
  expected={168600:[400084,400089],168601:[400094,400099],168602:[400036,400051],168603:[400158,400164]}
  for item in new:
   self.assertEqual(item['option_groups'],{'1':expected[item['template']]});self.assertTrue(item['identified'])
   self.assertFalse(item.get('artifact_socket_open',False));self.assertEqual(item['count'],1)
  self.assertEqual(len({i['uid']for i in new if i['template']==168603}),2)
  self.assertFalse(any(i['uid']==box['uid']for i in after))
  saved=self.snapshot();self.use(box,'artifact-fixed');self.assertEqual(self.snapshot(),saved)
  cold=LocalAccount(LocalState(self.path,self.uid));cold.enable_characters();self.assertEqual(cold.get_inventory_snapshot()['items'],after)
  second=self.grant(723618)
  with patch('els_server.protocol.protocol_codec.encode_event',side_effect=ValueError('artifact-late-codec')):
   self.reject(lambda:self.use(second,'artifact-late-failure'))
  with closing(sqlite3.connect(self.path))as db:self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
  ROWS.append(dict(template=723618,outputs=5,ring_UIDs=2,fixed_ordinary_effects=True,identified=True,empty_spirit=True,unexpanded=True,replay_no_increment=True,cold=True,late_encoder_atomic=True))
if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:],Boxes)if len(sys.argv)>1 else unittest.defaultTestLoader.loadTestsFromTestCase(Boxes)
 result=unittest.TextTestRunner(verbosity=2).run(suite)
 report=dict(ok=result.wasSuccessful(),tests=result.testsRun,errors=[s for _,s in result.errors],failures=[s for _,s in result.failures],rows=ROWS,natural_GUI=False,installed=False)
 (HOME/('tests-owned-final.json'if len(sys.argv)>1 else 'tests-final-v2.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(report,ensure_ascii=False));sys.exit(not result.wasSuccessful())
