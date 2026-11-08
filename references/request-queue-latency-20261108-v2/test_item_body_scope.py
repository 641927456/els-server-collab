"""Pure wire-cache behavior; no SQL/ownership checks are cached here."""
import bootstrap
import copy,json,unittest
from els_server.storage.read_scope import committed_reads,item_body_projection

class ItemBodyScope(unittest.TestCase):
 def setUp(self):
  self.calls=[]
  def encode(item):
   self.calls.append(item['uid'])
   return json.dumps({k:v for k,v in item.items()if k not in('uid','slot')},sort_keys=True).encode()
  self.encode=encode
 def body(self,item):
  return item_body_projection(item,self.encode,wire_key={k:v for k,v in item.items()if k not in('uid','slot')})
 def item(self,uid=1001,**kw):
  return dict(uid=uid,slot=uid-1001,template=1,metadata=0,group=1,count=1,**kw)
 def test_different_instances_do_not_evict_each_other(self):
  a=self.item(options={'1':[1,2]});b=self.item(1002,options={'1':[3,4]})
  with committed_reads():
   original=[self.body(a),self.body(b)]
   self.assertEqual([self.body(copy.deepcopy(a)),self.body(copy.deepcopy(b))],original)
  self.assertEqual(self.calls,[1001,1002])
 def test_identical_stacks_still_share_body(self):
  with committed_reads():
   self.assertEqual(self.body(self.item()),self.body(self.item(1002)))
   self.body(self.item())
  self.assertEqual(self.calls,[1001])
 def test_changed_nested_state_encodes_current_value(self):
  a=self.item(options={'1':[1,2]})
  with committed_reads():
   before=self.body(a);a['options']['1'][1]=9;after=self.body(a)
  self.assertNotEqual(before,after);self.assertEqual(self.calls,[1001,1001])
 def test_changed_expiry_and_count_do_not_reuse_old_body(self):
  a=self.item(expires_at=123)
  with committed_reads():
   before=self.body(a);a['expires_at']=124;after=self.body(a);a['count']=2;last=self.body(a)
  self.assertEqual(len({before,after,last}),3);self.assertEqual(len(self.calls),3)
 def test_no_cross_operation_reuse(self):
  for _ in range(2):
   with committed_reads():self.body(self.item())
  self.assertEqual(self.calls,[1001,1001])
 def test_default_key_keeps_original_current_instance_behavior(self):
  a=self.item()
  with committed_reads():
   before=item_body_projection(a,self.encode);self.assertEqual(item_body_projection(a,self.encode),before)
   a['slot']=9;item_body_projection(a,self.encode)
  self.assertEqual(len(self.calls),2)

if __name__=='__main__':unittest.main(argv=[__file__],verbosity=2)
