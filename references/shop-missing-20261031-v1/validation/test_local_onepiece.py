from pathlib import Path
import json,sqlite3,struct,sys,tempfile,unittest
from unittest.mock import patch
from contextlib import closing
C=Path(__file__).resolve().parent/'local-candidate';sys.path.insert(0,str(C))
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.shop_state import catalog,purchase
from els_server.storage.inventory_state import grant_items,load_items
from els_server.domain.fashion_singles import definitions,onepiece_templates
from els_server.domain.acquisition_policy import can_acquire

class StorefrontTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent,prefix="storefront-boundary-");self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'store.sqlite3';self.roles={}
  for role in(1,13,14,15):
   a=LocalAccount(LocalState(self.path),account_id=role);a.enable_characters();self.roles[role]=a.characters.create('StoreTest'+str(role),role,'create:'+str(role))['uid']
  with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE reward_balances SET ed=200000')
 def snapshot(self):
  with closing(sqlite3.connect(self.path))as db,db:return tuple(db.iterdump())
 def request(self,t):return struct.pack('>IIH',1,1200000000+t,1)
 def test_all962_visible_and_role_specific(self):
  rows=[r for r in definitions()if r['category']==17];self.assertEqual(len(rows),962);self.assertEqual(onepiece_templates(),{r['template']for r in rows})
  for role in range(1,16):
   wanted={r['template']for r in rows if r['role']==role};actual={p['template']for p in catalog(role)if p['category']==17};self.assertEqual(actual,wanted)
 def test_special_onepieces_only_gain_storefront_source(self):
  for role,t in((13,307689),(14,316095),(15,333343)):
   self.assertFalse(can_acquire(t));uid=self.roles[role];before=self.snapshot()
   with closing(sqlite3.connect(self.path))as db,db:
    with self.assertRaises(ValueError):grant_items(db,[dict(template=t,metadata=0,group=7,quantity=1)],uid)
   self.assertEqual(self.snapshot(),before)
   result=purchase(self.path,self.request(t),'store:'+str(t),uid);self.assertEqual(purchase(self.path,self.request(t),'store:'+str(t),uid),result)
   with closing(sqlite3.connect(self.path))as db,db:
    self.assertEqual(db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()[0],199950);self.assertEqual(sum(i['template']==t for i in load_items(db,uid)),1)
 def test_wrong_role_refused_without_increment(self):
  before=self.snapshot()
  with self.assertRaises(ValueError):purchase(self.path,self.request(333343),'wrong-role',self.roles[1])
  self.assertEqual(self.snapshot(),before)
 def test_encoder_failure_rolls_back_items_money_and_receipt(self):
  before=self.snapshot()
  with patch('els_server.storage.shop_state.ed_purchase_ack',side_effect=RuntimeError('fixture encode failure')):
   with self.assertRaises(RuntimeError):purchase(self.path,self.request(333343),'encode-failure',self.roles[15])
  self.assertEqual(self.snapshot(),before)
 def test_nonfashion_source_and_absent_grant_refused(self):
  for source,plan in((frozenset({77000}),[dict(template=77000,metadata=2,group=6,quantity=1)]),(frozenset({333343}),[dict(template=77000,metadata=2,group=6,quantity=1)])):
   before=self.snapshot()
   with closing(sqlite3.connect(self.path))as db,db:
    with self.assertRaises(ValueError):grant_items(db,plan,self.roles[1],shop_fashion_templates=source)
   self.assertEqual(self.snapshot(),before)

if __name__=='__main__':unittest.main()
