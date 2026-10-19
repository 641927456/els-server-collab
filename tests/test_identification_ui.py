"""Original reset -> identify workflow, ownership, retries and persistence."""
import sqlite3,struct,unittest
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from tests import test_npc_sale as fixture
from tests.test_bank_state import payload as bank_payload
from els_server.domain.identification_ui import catalog,draw
from els_server.storage.identification_ui import perform
from els_server.storage.bank_state import transfer,snapshot
from els_server.protocol.identification_messages import request
from els_server.domain.local_session import LocalSession
from els_server.protocol.protocol_codec import Event
def identify(uid):return struct.pack('>QB Ii',uid,0,0,0)
def reset(scroll,uid):return struct.pack('>QQ',scroll,uid)
class IdentificationUITests(unittest.TestCase):
 grant=fixture.SaleTests.grant;items=fixture.SaleTests.items;dump=fixture.SaleTests.dump;money=fixture.SaleTests.money
 def setUp(self):
  fixture.SaleTests.setUp(self);self.target=self.grant(61885);self.scroll=self.grant(287960,3)
 def now(self):return next(i for i in self.items() if i['uid']==self.target['uid'])
 def clear(self,op='reset'):
  return perform(self.path,1001,0x43a,reset(self.scroll['uid'],self.target['uid']),op)
 def test_reset_consumes_scroll_marks_unidentified_then_identify_rolls_once(self):
  before=self.money();self.assertEqual(self.clear()[0].kind,0x43b);self.assertFalse(self.now()['identified']);self.assertEqual(self.now()['option_groups'],{'1':[]})
  answer=perform(self.path,1001,0x438,identify(self.target['uid']),'identify',lambda n:9999)
  self.assertEqual(answer[0].kind,0x439);self.assertTrue(self.now()['identified']);self.assertEqual(self.now()['option_groups']['1'],[draw(9999)])
  self.assertEqual(next(i['count'] for i in self.items() if i['uid']==self.scroll['uid']),2);self.assertEqual(self.money(),before)
  cold=fixture.LocalAccount(fixture.LocalState(self.path));self.assertEqual(next(i for i in cold.get_inventory_snapshot()['items'] if i['uid']==self.target['uid']),self.now())
 def test_initially_identified_item_cannot_be_rerolled_for_free(self):
  before=self.dump()
  with self.assertRaises(ValueError):perform(self.path,1001,0x438,identify(self.target['uid']),'free',lambda n:0)
  self.assertEqual(self.dump(),before);self.clear();before=self.dump()
  with self.assertRaises(ValueError):self.clear('second-scroll')
  self.assertEqual(self.dump(),before)
 def test_retries_return_current_state_after_later_rerolls(self):
  p=identify(self.target['uid']);self.clear();perform(self.path,1001,0x438,p,'one',lambda n:0)
  self.clear('reset2');perform(self.path,1001,0x438,p,'two',lambda n:9999);before=self.dump()
  perform(self.path,1001,0x438,p,'one',lambda n:self.fail('Redraw'));self.clear('reset');self.assertEqual(self.dump(),before)
  self.assertEqual(self.now()['option_groups']['1'],[draw(9999)])
 def test_encoder_failure_and_random_failure_roll_back_flag_options_scroll_and_receipt(self):
  before=self.dump()
  with patch('els_server.storage.identification_ui.acknowledgement',side_effect=ValueError('wire')):
   with self.assertRaises(ValueError):self.clear()
  self.assertEqual(self.dump(),before);self.clear();before=self.dump()
  for roll in (-1,10000,True):
   with self.assertRaises(ValueError):perform(self.path,1001,0x438,identify(self.target['uid']),'rng',lambda n:roll)
   self.assertEqual(self.dump(),before)
 def test_every_probability_boundary_is_an_original_option(self):
  self.assertEqual(len(catalog()['outcomes']),45);start=0
  for row in catalog()['outcomes']:
   self.assertEqual(draw(start),row['option']);self.assertEqual(draw(start+row['weight']-1),row['option']);start+=row['weight']
  self.assertEqual(start,10000)
 def test_shared_bank_transfers_identification_flags_and_options(self):
  self.clear();perform(self.path,1001,0x438,identify(self.target['uid']),'roll',lambda n:0);item=self.now()
  transfer(self.path,1001,bank_payload((1,item['slot']),(16,0),item),'deposit')
  self.assertEqual(snapshot(self.path,self.other)['bank_items'][0]['item']['option_groups'],item['option_groups'])
  transfer(self.path,self.other,bank_payload((16,0),(1,0),item),'withdraw')
  with closing(sqlite3.connect(self.path)) as db:
   from els_server.storage.inventory_state import load_items
   other=load_items(db,self.other)[0];self.assertEqual(other['option_groups'],item['option_groups']);self.assertTrue(other['identified']);self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
 def test_wrong_owner_material_target_locked_and_malformed_packets(self):
  for owner,p in ((self.other,reset(self.scroll['uid'],self.target['uid'])),(1001,reset(self.gear['uid'],self.target['uid'])),(1001,reset(self.scroll['uid'],self.gear['uid']))):
   before=self.dump()
   with self.assertRaises(ValueError):perform(self.path,owner,0x43a,p,'bad')
   self.assertEqual(self.dump(),before)
  from els_server.storage.item_locks import assign
  with closing(sqlite3.connect(self.path)) as db,db:db.execute('BEGIN IMMEDIATE');assign(db,1001,self.target['uid'],2200000000)
  before=self.dump()
  with self.assertRaises(ValueError):self.clear()
  self.assertEqual(self.dump(),before)
  for kind,p in ((0x438,b''),(0x43a,b''),(0x438,identify(0)),(0x438,struct.pack('>QBIi',self.target['uid'],1,0,0)),(0x43a,reset(0,self.target['uid']))):
   with self.assertRaises(ValueError):request(kind,p)
 def test_concurrent_identification_draws_once(self):
  self.clear();p=identify(self.target['uid']);calls=[]
  def rng(n):calls.append(n);return 0
  with ThreadPoolExecutor(2) as pool:list(pool.map(lambda _:perform(self.path,1001,0x438,p,'same',rng),range(2)))
  self.assertEqual(calls,[10000])
 def test_ui_reset_and_evaluate_routes_and_failures(self):
  s=LocalSession(self.account,enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True)
  s.role='game';s.phase='town_ready'
  for sequence,kind,p in ((1,0x43a,reset(self.scroll['uid'],self.target['uid'])),(2,0x438,identify(self.target['uid']))):
   answer=s.handle(Event(0x202,kind=kind,payload=p),sequence);self.assertEqual(answer[0].kind,kind+1);self.assertEqual(struct.unpack_from('>i',answer[0].payload)[0],0)
  before=self.dump();s.phase='dungeon_active';reply=s.handle(Event(0x202,kind=0x43a,payload=b''),3)
  self.assertEqual(struct.unpack_from('>i',reply[0].payload)[0],-1);self.assertEqual(self.dump(),before)
if __name__=='__main__':unittest.main()
