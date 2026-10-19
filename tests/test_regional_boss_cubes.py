"""Official regional cube boundaries, atomic rewards, retries and preview."""
import sqlite3,struct,unittest
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from tests import test_npc_sale as fixture
from tests.test_fixed_cubes import payload
from els_server.storage.fixed_cubes import open_cube
from els_server.domain.regional_boss_cubes import catalog,draw
from els_server.domain.local_session import LocalSession
from els_server.protocol.protocol_codec import Event
class RegionalBossCubeTests(unittest.TestCase):
 setUp=fixture.SaleTests.setUp;grant=fixture.SaleTests.grant;items=fixture.SaleTests.items;dump=fixture.SaleTests.dump;money=fixture.SaleTests.money
 def test_every_original_outcome_and_weight_boundary(self):
  self.assertEqual(set(catalog()),{313105,313106,313107});self.assertEqual(sum(len(r['entries']) for r in catalog().values()),16)
  for t,row in catalog().items():
   self.assertEqual(sum(e['weight'] for e in row['entries']),10000);start=0
   for e in row['entries']:
    self.assertEqual(draw(row,start),e);self.assertEqual(draw(row,start+e['weight']-1),e)
    item=self.grant(t);before=self.money();events=open_cube(self.path,1001,t,payload(item['uid']),str(item['uid']),lambda n:start)
    self.assertEqual(struct.unpack_from('>ii',events[-1].payload,16),(e['template'],1));self.assertEqual(self.money(),before)
    self.assertNotIn(item['uid'],{i['uid'] for i in self.items()});self.assertTrue(any(i['template']==e['template'] and i['group']==2 for i in self.items()));start+=e['weight']
 def test_retry_after_exhaustion_does_not_redraw_reward_or_repeat_popup(self):
  item=self.grant(313106);p=payload(item['uid']);open_cube(self.path,1001,313106,p,'once',lambda n:0);before=self.dump()
  answer=open_cube(self.path,1001,313106,p,'once',lambda n:self.fail('Redraw'))
  self.assertEqual(self.dump(),before);self.assertEqual([e.kind for e in answer][-1],0x197);self.assertEqual(struct.unpack_from('>I',answer[-1].payload,12)[0],0)
 def test_encoder_bag_full_invalid_random_and_foreign_owner_rollback(self):
  item=self.grant(313107,2);p=payload(item['uid']);before=self.dump()
  for roll in (-1,10000,True):
   with self.assertRaises(ValueError):open_cube(self.path,1001,313107,p,'invalid',lambda n:roll)
   self.assertEqual(self.dump(),before)
  for name in ('els_server.storage.fixed_cubes.result','els_server.storage.fixed_cubes.grant_items'):
   with patch(name,side_effect=ValueError('fail')):
    with self.assertRaises(ValueError):open_cube(self.path,1001,313107,p,'fail',lambda n:0)
   self.assertEqual(self.dump(),before)
  with self.assertRaises(ValueError):open_cube(self.path,self.other,313107,p,'foreign',lambda n:0)
  self.assertEqual(self.dump(),before)
 def test_concurrent_duplicates_deliver_one_draw(self):
  item=self.grant(313106,2);p=payload(item['uid']);calls=[]
  def rng(n):calls.append(n);return 0
  with ThreadPoolExecutor(2) as pool:list(pool.map(lambda _:open_cube(self.path,1001,313106,p,'same',rng),range(2)))
  self.assertEqual(calls,[10000]);self.assertEqual(sum(i['count'] for i in self.items() if i['template']==30607),1)
  self.assertEqual(next(i['count'] for i in self.items() if i['uid']==item['uid']),1)
 def test_owned_preview_and_use_are_routed_without_ice_mode(self):
  item=self.grant(313105);s=LocalSession(self.account,enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True)
  s.role='game';s.phase='town_ready'
  reply=s.handle(Event(0x202,kind=0x559,payload=struct.pack('>iIBB',313105,0,0,0)),1)
  self.assertEqual(reply[0].kind,0x55a);self.assertEqual(struct.unpack_from('>i',reply[0].payload)[0],0)
  answer=s.handle(Event(0x202,kind=0x196,payload=payload(item['uid'])),2);self.assertEqual(answer[-1].kind,0x197)
  self.assertTrue(any(i['group']==2 for i in self.items()))
if __name__=='__main__':unittest.main()
