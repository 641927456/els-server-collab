from contextlib import closing
from unittest.mock import patch
import json,sqlite3,struct,time,unittest
import test_common as f
from els_server.domain.acquisition_policy import can_acquire
from els_server.storage.inventory_state import grant_items
from els_server.domain.tenebros_capacity_flow import selected
from els_server.storage.fixed_cubes import open_cube

class Boundary(f.Common):
 def test_retained_grants_stay_closed_and_original_actor_required(self):
  for t in(723610,723618):
   self.assertFalse(can_acquire(t))
   def generic(t=t):
    with closing(sqlite3.connect(self.path))as db,db:
     db.execute('BEGIN IMMEDIATE');grant_items(db,[dict(template=t,metadata=f.VERIFIED_TEMPLATES[t],group=4,quantity=1)],self.uid)
   self.reject(generic)
  path,owner,aid,prepare=selected(self.s)
  for t in(723612,723673):
   box=self.grant(t)
   self.s.handle(f.Event(0x202,performers=(0,),kind=0x559,payload=struct.pack('>iIiBB',t,1,0,0,0)),80)
   self.reject(lambda:open_cube(path,owner,t,f.base.wire(box['uid']),'no-current-actor',account_id=aid))
   self.reject(lambda:open_cube(path,owner,t,f.base.wire(box['uid']),'foreign-account',account_id=aid+999,prepare=prepare))
   def missing_debit():
    from els_server.domain.owned_growth_items import issue_source,reward_plan
    with closing(sqlite3.connect(self.path))as db,db:
     db.execute('BEGIN IMMEDIATE');issue_source(db,owner,aid,'no-debit',box,reward_plan(t),prepare)
   self.reject(missing_debit)
 def test_parent_capacity_lock_and_foreign_character_reject_without_spend(self):
  from els_server.storage.bag_capacity import allowances
  from els_server.storage.item_locks import assign
  for t in(723612,723673):
   box=self.grant(t)
   self.s.handle(f.Event(0x202,performers=(0,),kind=0x559,payload=struct.pack('>iIiBB',t,1,0,0,0)),80)
   with closing(sqlite3.connect(self.path))as db:limits=allowances(db,self.uid)
   limits[4]=max(i['slot']for i in self.items()if i['group']==4)+1
   with patch('els_server.storage.bag_capacity.allowances',return_value=limits):self.failed(box,sequence=t)
   with closing(sqlite3.connect(self.path))as db,db:
    db.execute('BEGIN IMMEDIATE');assign(db,self.uid,box['uid'],int(time.time())+300)
   self.failed(box,sequence=t+1)
   self.s.account=self.root.for_character(self.other)
   try:
    self.s.handle(f.Event(0x202,performers=(0,),kind=0x559,payload=struct.pack('>iIiBB',t,1,0,0,0)),81)
    self.failed(box,sequence=t+2)
   finally:self.s.account=self.account
 def test_nested_artifact_singletons_and_title_stack_survive_cold_read(self):
  parent=self.grant(723612,count=2)
  for count,seq in((1,500),(0,501)):
   response=self.send(parent,count=count,sequence=seq);self.assertEqual(struct.unpack_from('>i',f.base.ack(response,0x197).payload)[0],0)
  artifacts=[i for i in self.items()if i['template']==723618]
  self.assertEqual(len(artifacts),2);self.assertEqual([i['count']for i in artifacts],[1,1])
  for n,artifact in enumerate(artifacts):
   response=self.send(artifact,sequence=502+n);self.assertEqual(struct.unpack_from('>i',f.base.ack(response,0x197).payload)[0],0)
  rings=[i for i in self.items()if i['template']==168603]
  self.assertEqual(len(rings),4);self.assertEqual(len({i['uid']for i in rings}),4)
  for i in rings:
   self.assertEqual(i['option_groups'],{'1':[400158,400164]});self.assertFalse(i.get('artifact_socket_open',False))
  for seq in(510,511):
   box=self.grant(723673);response=self.send(box,sequence=seq);self.assertEqual(struct.unpack_from('>i',f.base.ack(response,0x197).payload)[0],0)
  self.assertEqual(sorted(i['count']for i in self.items()if i['template']==723610),[1,999])
  cold=f.LocalAccount(f.LocalState(self.path,self.uid));cold.enable_characters();self.assertEqual(cold.get_inventory_snapshot()['items'],self.items())

if __name__=='__main__':
 import sys
 names=[n for n in Boundary.__dict__ if n.startswith('test_')and(len(sys.argv)==1 or n in sys.argv[1:])]
 result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(Boundary(n)for n in names))
 out=dict(ok=result.wasSuccessful(),tests=result.testsRun,errors=[s for _,s in result.errors],failures=[s for _,s in result.failures])
 (f.H/'boundary-result.json').write_text(json.dumps(out,indent=2),encoding='utf8');raise SystemExit(not result.wasSuccessful())
