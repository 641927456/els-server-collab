"""Count1 regression for the isolated portable patch; historical sources stay frozen."""
import importlib.util,sqlite3,struct,unittest
from contextlib import closing
from pathlib import Path
from tests import test_growing_adventure_kit_current as helper
ROOT=Path(__file__).resolve().parents[1]
path=ROOT/'references/growing-kit-count-one-20261031-v1/portable/els_server/storage/fixed_cubes.py'
spec=importlib.util.spec_from_file_location('count_one_candidate',path);candidate=importlib.util.module_from_spec(spec);spec.loader.exec_module(candidate)
class CubeSingleCountTests(unittest.TestCase):
 setUp=helper.GrowingAdventureKitTests.setUp
 items=helper.GrowingAdventureKitTests.items
 grant=helper.GrowingAdventureKitTests.grant
 snapshot=helper.GrowingAdventureKitTests.snapshot
 reject=helper.GrowingAdventureKitTests.reject
 def open(self,item,op='single',**kw):return candidate.open_cube(self.path,self.uid,168889,helper.wire(item['uid'],**kw),op)
 def test_explicit_single_count_is_atomic_and_replayable(self):
  box=self.grant(168889,2)[0];before=self.items();ed=self.account.get_reward_balances()['ed']
  for count in (-1,2,99):self.reject(lambda count=count:self.open(box,'bad-count-'+str(count),option=count))
  answer=self.open(box,'explicit-single',option=1);self.assertEqual(struct.unpack_from('>iiiI',answer[-1].payload),(0,0,0,5))
  new=[i for i in self.items()if i['uid']not in {r['uid']for r in before}]
  self.assertEqual({i['template']:i['count']for i in new},{r['template']:r['quantity']for r in helper.outputs_for(1)})
  self.assertEqual(len(new),5);self.assertEqual(next(i['count']for i in self.items()if i['uid']==box['uid']),1)
  saved=self.snapshot();self.open(box,'explicit-single',option=1);self.assertEqual(self.snapshot(),saved)
  self.assertEqual(self.account.get_reward_balances()['ed'],ed)
  cold=helper.LocalAccount(helper.LocalState(self.path,self.uid));cold.enable_characters();self.assertEqual(cold.get_inventory_snapshot()['items'],self.items())
 def test_explicit_single_capacity_rollback(self):
  box=self.grant(168889)[0]
  with closing(sqlite3.connect(self.path))as db:cap=helper.allowances(db,self.uid)[1]
  fillers=self.grant(60100,cap-4-sum(i['group']==1 for i in self.items()))
  self.reject(lambda:self.open(box,'four-free',option=1),helper.InventoryFull)
  with closing(sqlite3.connect(self.path))as db,db:db.execute('BEGIN IMMEDIATE');helper.remove(db,self.uid,fillers[0])
  answer=self.open(box,'five-free',option=1);self.assertEqual(struct.unpack_from('>iiiI',answer[-1].payload),(0,0,0,5))
if __name__=='__main__':unittest.main()
