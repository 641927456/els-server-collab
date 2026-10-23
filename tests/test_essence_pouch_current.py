"""Changed singleton bag constraints only; no original native reruns."""
import hashlib,json,sqlite3,struct,sys,tempfile,time,unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
from els_server.domain.local_session import LocalAccount
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS,validate_item
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items,InventoryFull
from els_server.storage import fixed_cubes,bag_moves,inventory_actions
from els_server.storage.character_selection import save
from els_server.storage.character_lifecycle import change,DAY
from els_server.storage.equipment_receipt_state import current_changes
from els_server.protocol.ice_messages import use_request
ROWS=[]
def wire(uid):return struct.pack('>QBBBIi',uid,0,0,0,0,0)
class Check(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='essence-singleton-v2-');self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'game.sqlite3';self.account=LocalAccount(LocalState(self.path));self.account.enable_characters();self.now=int(time.time())
 def grant(self,t,n=1,**extra):
  with closing(sqlite3.connect(self.path))as db,db:db.execute('BEGIN IMMEDIATE');return grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=n,**extra)],1001)
 def items(self):
  with closing(sqlite3.connect(self.path))as db:return load_items(db,1001)
 def dump(self):
  with closing(sqlite3.connect(self.path))as db:return tuple(db.iterdump())
 def open(self,item,op='owned'):return fixed_cubes.open_cube(self.path,1001,723604,wire(item['uid']),op)
 def test_two_distinct_bags_cap1000_receipt_current_identity_cold(self):
  self.assertEqual((TEMPLATE_MAX_STACKS[723604],TEMPLATE_MAX_STACKS[723609]),(1,1000));bags=self.grant(723604,2);self.assertEqual([i['count']for i in bags],[1,1]);self.assertNotEqual(bags[0]['uid'],bags[1]['uid'])
  original=self.grant(723609,950)[0];ed=self.account.get_reward_balances()['ed'];events=self.open(bags[0]);outputs=[i for i in self.items()if i['template']==723609];self.assertEqual(sorted(i['count']for i in outputs),[50,1000]);self.assertNotIn(bags[0]['uid'],[i['uid']for i in self.items()]);self.assertIn(bags[1],self.items());self.assertEqual(self.account.get_reward_balances()['ed'],ed)
  remainder=next(i for i in outputs if i['count']==50);bag_moves.move_bag_items(self.path,struct.pack('>BiBiB',4,remainder['slot'],4,34,0),1001);inventory_actions.discard(self.path,1001,struct.pack('>Qi',original['uid'],1000),'remove-old-UID')
  replacement=self.grant(130172)[0]
  if replacement['slot']!=original['slot']:bag_moves.move_bag_items(self.path,struct.pack('>BiBiB',4,replacement['slot'],4,original['slot'],0),1001)
  seen=[];original_refresh=fixed_cubes.current_changes
  def capture(*a,**kw):
   rows=original_refresh(*a,**kw);seen.extend(rows);return rows
  before=self.dump()
  with patch.object(fixed_cubes,'current_changes',side_effect=capture):replay=self.open(bags[0])
  self.assertEqual(self.dump(),before);current=[i for p,i in seen if i is not None];self.assertIn((remainder['uid'],34,50),[(i['uid'],i['slot'],i['count'])for i in current]);self.assertIn(replacement['uid'],[i['uid']for i in current]);self.assertNotIn(original['uid'],[i['uid']for i in current]);self.assertEqual(struct.unpack_from('>iiiI',replay[-1].payload),(0,0,0,0))
  cold=LocalAccount(LocalState(self.path));cold.enable_characters()
  with closing(sqlite3.connect(self.path))as db:self.assertEqual(cold.get_inventory_snapshot()['items'],load_items(db,1001));self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
  ROWS.append(dict(case='singleton-distinct-UID1bag100-output-cap1000-current-receipt-cold',passed=True))
  save(self.path,1,[],[1001])
  with patch('els_server.storage.character_lifecycle.current_time',return_value=self.now):change(self.path,1,1001,'schedule')
  before=self.dump()
  with self.assertRaisesRegex(ValueError,'pending deletion'):self.open(bags[1],'pending-new')
  self.assertEqual(self.dump(),before)
  with patch('els_server.storage.character_lifecycle.current_time',return_value=self.now+3*DAY+1):change(self.path,1,1001,'finalize')
  for item,op in((bags[0],'owned'),(bags[1],'finalized-new')):
   before=self.dump()
   with self.assertRaisesRegex(ValueError,'pending deletion or finalized'):self.open(item,op)
   self.assertEqual(self.dump(),before)
  ROWS.append(dict(case='singleton-pending-new-finalized-new-and-committed-reject',SQL_zero=True))
 def test_singleton_full_capacity_and_fault_rollbacks(self):
  bag=self.grant(723604)[0]
  with self.assertRaises(ValueError):validate_item(dict(bag,count=2))
  before=self.dump()
  for label,symbol,error in(('capacity-fault','grant_items',InventoryFull('private capacity fault')),('encoder-fault','result',ValueError('private encoder fault'))):
   with patch.object(fixed_cubes,symbol,side_effect=error):
    with self.assertRaises(type(error)):self.open(bag,label)
   self.assertEqual(self.dump(),before);ROWS.append(dict(case=label,SQL_zero=True,fault_injection=True))
  occupied=sum(i['group']==4 for i in self.items());self.grant(130208,36-occupied);self.open(bag,'real-full');self.assertEqual(sum(i['group']==4 for i in self.items()),36);out=next(i for i in self.items()if i['template']==723609);self.assertEqual((out['slot'],out['count']),(bag['slot'],100));ROWS.append(dict(case='real-full-bag-uses-consumed-source-slot',passed=True))

if __name__=='__main__':unittest.main()
