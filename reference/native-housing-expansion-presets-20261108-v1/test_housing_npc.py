"""Original merchant acquisition, preserving source-only generic grants."""
from test_housing_storage import HousingStorageTests,F
from unittest.mock import patch
import hashlib,json,sqlite3,struct,sys,unittest
from els_server.storage import npc_trade,inventory_state,housing_layouts,achievements
from els_server.domain import npc_trade as rules
from els_server.domain.acquisition_policy import can_acquire
from els_server.protocol.housing_layout_messages import REQUEST,encode

class HousingNpcTests(HousingStorageTests):
 def fund(self,amount=500000000):
  with self.db()as db,db:db.execute('UPDATE reward_balances SET ed=? WHERE uid=?',(amount,self.uid))
 def buy(self,entries,operation,merchant=10018):
  payload=struct.pack('>BHI',0,0,len(entries))+b''.join(struct.pack('>ii',*r)for r in entries)+struct.pack('>i',merchant)
  return npc_trade.purchase(self.path,self.uid,self.a.get_location()['map'],payload,operation)
 def test_four_native_furniture_prices_purchase_cold_and_replay(self):
  self.fund();entries=[(t,1)for t in(570011,570012,570015,570016)]
  expected=sum(rules.price(t)*n for t,n in entries);self.buy(entries,'owned-four-furniture')
  with self.db()as db:
   rows=[i for i in inventory_state.load_items(db,self.uid)if i['group']==25]
   self.assertEqual({i['template']for i in rows},{t for t,q in entries});self.assertEqual(len(rows),4)
   self.assertEqual(db.execute('SELECT ed FROM reward_balances WHERE uid=?',(self.uid,)).fetchone(),(500000000-expected,))
   self.assertEqual(db.execute('SELECT kind FROM raid_reward_sources WHERE operation_id=?',('owned-four-furniture',)).fetchone(),('npc_trade',))
  before=self.dump();self.buy(entries,'owned-four-furniture');self.assertEqual(self.dump(),before)
  for t,q in entries:self.assertFalse(can_acquire(t))
  with self.db()as db,db:
   db.execute('BEGIN IMMEDIATE')
   with self.assertRaises(ValueError):inventory_state.grant_items(db,[dict(template=570011,metadata=0,group=25,quantity=1)],self.uid)
  self.assertEqual(self.dump(),before)
 def test_merchant_mixed_source_only_and_existing_quest_furniture(self):
  self.fund();self.buy([(570011,1),(570014,1)],'owned-mixed-furniture')
  with self.db()as db:
   self.assertEqual({i['template']for i in inventory_state.load_items(db,self.uid)if i['group']==25},{570011,570014})
 def test_wrong_merchant_and_insufficient_ED_roll_back(self):
  before=self.dump()
  with self.assertRaises(ValueError):self.buy([(570011,1)],'owned-wrong-merchant',10000)
  self.assertEqual(self.dump(),before)
  with self.assertRaises(ValueError):self.buy([(570011,1)],'owned-poor-merchant')
  self.assertEqual(self.dump(),before)
 def test_full_bag_rolls_back_price_and_source_ledger(self):
  self.fund();self.placed(560);before=self.dump()
  with self.assertRaises(inventory_state.InventoryFull):self.buy([(570011,1)],'owned-full-merchant')
  self.assertEqual(self.dump(),before)
 def test_unknown_template_remains_explicit_rejection(self):
  self.fund();before=self.dump()
  with self.assertRaises(ValueError):self.buy([(2147483647,1)],'owned-unknown-merchant')
  self.assertEqual(self.dump(),before)
 def test_changed_merchant_actor_rolls_back_source_and_price(self):
  self.fund();before=self.dump();original=npc_trade.grant_items
  def change_then_grant(db,plan,owner,**kwargs):
   db.execute('UPDATE location SET town=20013 WHERE uid=?',(owner,))
   return original(db,plan,owner,**kwargs)
  with patch.object(npc_trade,'grant_items',side_effect=change_then_grant):
   with self.assertRaises(ValueError):self.buy([(570011,1)],'owned-stale-merchant')
  self.assertEqual(self.dump(),before)
 def test_200_original_merchant_furniture_to_layout_and_achievement(self):
  self.fund()
  for n,q in enumerate((99,99,2)):self.buy([(570014,q)],'owned-200-furniture-'+str(n))
  with self.db()as db:
   rows=[i for i in inventory_state.load_items(db,self.uid)if i['template']==570014]
   self.assertEqual(len(rows),200);self.assertEqual(db.execute('SELECT ed FROM reward_balances WHERE uid=?',(self.uid,)).fetchone(),(100000000,))
  layout=([(i['uid'],(1,i['uid'],570014,n%24,n//24,0))for n,i in enumerate(rows)],[],[],0,0,0)
  self.save(layout,'owned-200-merchant-layout')
  with self.db()as db:
   self.assertEqual(len(housing_layouts.snapshot(db,self.uid,self.account)['layout'][0]),200)
   progress=dict(db.execute('SELECT achievement,value FROM native_achievement_progress WHERE account_id=?AND achievement IN(376,377,378)',(self.account,)))
   self.assertEqual(progress,{376:200,377:200,378:200})

if __name__=='__main__':
 name=sys.argv[1];names=sys.argv[2:];result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(HousingNpcTests(n)for n in names))
 out=F/(name+'.json');assert not out.exists()
 out.write_text(json.dumps(dict(ok=result.wasSuccessful(),tests=result.testsRun,names=names,production_data=False,Game=False,App=False,natural_GUI=False,native_prices=True,details=[dict(test=str(t),error=e)for t,e in result.errors+result.failures]),indent=2)+'\n','utf8')
 raise SystemExit(0 if result.wasSuccessful()else 1)
