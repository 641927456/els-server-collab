from bootstrap import *
from verify_local_rules import *
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import unittest
from els_server.storage.inventory_state import grant_items
from els_server.domain.item_expiration import expired

class LocalEdges(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(prefix='local-edge-',dir=OUT);self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'save.sqlite3';initialize(self.path);self.owner=Characters(self.path).create('EdgeQA',1,'edge-qa')['uid'];a=LocalAccount(LocalState(self.path,self.owner));a.enable_characters();a.get_inventory_snapshot()
  cls=next(k for k,v in classes()[0].items()if v['family']==6 and v['stage']==0)
  with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE characters SET level=99,unit_type=6,unit_class=? WHERE uid=?',(cls,self.owner))
  self.character=dict(unit_type=6,unit_class=cls,level=99,active_unit=0)
 def prepare(self,db):require_owner(db,self.owner,1);require_active_character(db,self.owner)
 def seed(self,t,count):
  with closing(sqlite3.connect(self.path))as db,db:return seed(db,self.owner,t,count)
 def send(self,t,uid,count=2,op='edge',roll=lambda _:0):return open_cube(self.path,self.owner,t,wire(uid,count),op,roll,account_id=1,prepare=self.prepare)
 def test_all_primary_count_rejections(self):
  matrix=json.loads((OUT/'input272.json').read_bytes());templates=[r['template']for r in matrix]if isinstance(matrix,list)else[r['template']for r in matrix['rows']]
  for t in templates:
   with self.subTest(template=t):
    uid=self.seed(t,3);before=dump(self.path)
    for count in(-1,4,2147483647):
     with self.assertRaises(ValueError):self.send(t,uid,count,op='bad-'+str(t)+'-'+str(count))
     self.assertEqual(before,dump(self.path))
    with closing(sqlite3.connect(self.path))as db,db:db.execute('DELETE FROM inventory_items WHERE uid=?',(uid,))
 def test_key_shortage_second_draw_rolls_back(self):
  uid=self.seed(108902,3);self.seed(207500,1);before=dump(self.path)
  with self.assertRaises(ValueError):self.send(108902,uid)
  self.assertEqual(before,dump(self.path))
 def test_split_keys_and_final_slot_updates(self):
  uid=self.seed(108902,3);self.seed(207500,1);self.seed(207500,1);answer=self.send(108902,uid)
  after=items(self.path,self.owner);self.assertFalse(any(i['template']==207500 for i in after));self.assertEqual(next(i['count']for i in after if i['uid']==uid),1);self.assertTrue(rewards(answer))
 def test_alternate_keys_in_one_batch(self):
  keys=sorted({b['key']for b in branches_for(108900,self.character)})[:2];self.assertEqual(len(keys),2)
  uid=self.seed(108900,3)
  for key in keys:self.seed(key,1)
  before=totals(items(self.path,self.owner));answer=self.send(108900,uid);after=totals(items(self.path,self.owner))
  for key in keys:self.assertEqual(before[key]-after[key],1)
  self.assertEqual(sum(rewards(answer).values()),2)
 def test_locked_and_expired_key(self):
  from els_server.storage.item_locks import assign as lock
  from els_server.storage.item_expiration import assign as expiry
  uid=self.seed(108902,3);key=self.seed(207500,2)
  for setter,value in((lock,int(time.time())+3600),(expiry,int(time.time())-1)):
   with closing(sqlite3.connect(self.path))as db,db:
    db.execute('BEGIN IMMEDIATE')
    if setter is expiry:db.execute('DELETE FROM item_locks WHERE item_uid=?',(key,))
    setter(db,self.owner,key,value)
   before=dump(self.path)
   with self.assertRaises(ValueError):self.send(108902,uid)
   self.assertEqual(before,dump(self.path))
 def test_late_codec_and_second_factory_rollback(self):
  uid=self.seed(108902,3);self.seed(207500,2);before=dump(self.path)
  with patch('els_server.protocol.protocol_codec.encode_event',side_effect=ValueError('QA late encoding')):
   with self.assertRaises(ValueError):self.send(108902,uid)
  self.assertEqual(before,dump(self.path));calls=0
  def fault(*args,**kwargs):
   nonlocal calls
   calls+=1
   if calls==2:raise ValueError('QA second factory')
   return grant_items(*args,**kwargs)
  with patch('els_server.storage.fixed_cubes.grant_items',side_effect=fault):
   with self.assertRaises(ValueError):self.send(108902,uid)
  self.assertEqual(calls,2)
  self.assertEqual(before,dump(self.path))
 def test_source_only_new_rewards_reject_generic_grants(self):
  from els_server.domain.retained_box_openings import reader_definitions
  for row in reader_definitions():
   with closing(sqlite3.connect(self.path))as db,db:
    with self.assertRaises(ValueError):grant_items(db,[dict(template=row['template'],metadata=row['metadata'],group=row['group'],quantity=1)],self.owner)
 def test_self_reward_all_five_forms(self):
  for t in range(163346,163351):
   for count in(0,1,3):
    uid=self.seed(t,3);self.seed(163351,count or 1);before=totals(items(self.path,self.owner));answer=self.send(t,uid,count,op=f'self-{t}-{count}',roll=lambda _,t=t:t-163346);after=totals(items(self.path,self.owner));before[163351]-=count or 1;self.assertEqual(before,after);self.assertEqual(rewards(answer),{t:count or 1});self.assertIn(uid,{i['uid']for i in items(self.path,self.owner)})
    saved=dump(self.path);self.assertEqual(rewards(self.send(t,uid,count,op=f'self-{t}-{count}',roll=lambda _:self.fail('Replay RNG'))),{});self.assertEqual(saved,dump(self.path))
    with closing(sqlite3.connect(self.path))as db,db:
     db.execute('BEGIN IMMEDIATE')
     from els_server.storage.item_instances import remove
     for row in load_items(db,self.owner):
      if row['template']==t:remove(db,self.owner,row)
 def test_concurrent_same_and_competing_operations(self):
  uid=self.seed(108902,3);self.seed(207500,3)
  def send(op):
   try:return self.send(108902,uid,2,op)
   except ValueError:return None
  with ThreadPoolExecutor(2)as pool:answers=list(pool.map(send,('same','same')))
  self.assertEqual(sum(bool(rewards(a))for a in answers),1)
  self.assertEqual(next(i['count']for i in items(self.path,self.owner)if i['uid']==uid),1)
  with ThreadPoolExecutor(2)as pool:answers=list(pool.map(send,('other1','other2')))
  self.assertEqual(answers,[None,None])
 def test_scope_and_preview_keys(self):
  from els_server.domain.retained_box_openings import preview_outputs
  char=dict(unit_type=1,unit_class=1,active_unit=0,level=99)
  with self.assertRaises(ValueError):preview_outputs(108902,char,(207500,))
  char.update(unit_type=6,unit_class=6)
  self.assertEqual(preview_outputs(108902,char,(235140,)),preview_outputs(108902,char,(207500,)))
  with self.assertRaises(ValueError):preview_outputs(108902,char,(123456789,))

if __name__=='__main__':
 names=sys.argv[1:];suite=unittest.TestSuite(LocalEdges(n)for n in names)if names else unittest.defaultTestLoader.loadTestsFromTestCase(LocalEdges);result=unittest.TextTestRunner(verbosity=2).run(suite);report=dict(ok=result.wasSuccessful(),tests=result.testsRun,names=names,failures=[str(x)for x in result.failures],errors=[str(x)for x in result.errors]);(OUT/('local-edge-tests-affected.json'if names else'local-edge-tests.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8');raise SystemExit(not result.wasSuccessful())
