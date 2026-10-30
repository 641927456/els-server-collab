"""Atomic socket effects, current retries and complete instance persistence."""
import sqlite3,struct,unittest,json
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from tests import test_npc_sale as fixture
from tests.test_bank_state import payload as bank_payload
from els_server.storage.sage_sockets import socket,apply as socket_apply
from els_server.storage.equipment_options import replace
from els_server.storage.bank_state import transfer,snapshot
from els_server.domain.sage_sockets import capacity,catalog,draw,fee
from els_server.protocol.socket_messages import request
from els_server.domain.inventory_items import item_body,validate_item
from els_server.domain.local_session import LocalSession
from els_server.protocol.protocol_codec import Event
def payload(uid,materials,a=0,b=0):
 return struct.pack('>QI',uid,len(materials))+b''.join(struct.pack('>iQ',k,v) for k,v in materials.items())+struct.pack('>BBI6i',a,b,6,*([0]*6))
def apply_payload(uid,selected):
 return struct.pack('>QI',uid,len(selected))+b''.join(struct.pack('>iQ',k,v) for k,v in selected.items())
class SageSocketTests(unittest.TestCase):
 grant=fixture.SaleTests.grant;items=fixture.SaleTests.items;dump=fixture.SaleTests.dump;money=fixture.SaleTests.money
 def setUp(self):
  fixture.SaleTests.setUp(self);self.target=self.grant(11006011);self.stone=self.grant(135184,8)
  with closing(sqlite3.connect(self.path)) as db,db:db.execute('UPDATE reward_balances SET ed=100000000 WHERE uid=1001')
 def target_now(self):return next(i for i in self.items() if i['uid']==self.target['uid'])
 def test_paid_batch_relogin_and_exact_consumption(self):
  # 0x1C4 is the paid preview: it settles both stones and ED but only stages the
  # rolled values; the equipment carries them after the native 0x8B1 Apply.
  p=payload(self.target['uid'],{0:self.stone['uid'],1:self.stone['uid']});before=self.money();cost=fee(self.target)*2
  socket(self.path,1001,p,'both',lambda n:0,session_id='t')
  expected=[draw(self.target,0)]*2
  self.assertNotIn('option_groups',self.target_now())
  self.assertEqual(self.money(),before-cost);self.assertEqual(next(i['count'] for i in self.items() if i['uid']==self.stone['uid']),6)
  socket_apply(self.path,1001,apply_payload(self.target['uid'],{0:expected[0],1:expected[1]}),'both-apply',session_id='t')
  self.assertEqual(self.target_now()['option_groups'],{'0':expected})
  cold=fixture.LocalAccount(fixture.LocalState(self.path));self.assertEqual(next(i for i in cold.get_inventory_snapshot()['items'] if i['uid']==self.target['uid'])['option_groups'],{'0':expected})
 def test_preview_vector_carries_one_result_per_material_row(self):
  p=payload(self.target['uid'],{1:self.stone['uid']});events=socket(self.path,1001,p,'partial',lambda n:0,session_id='preview')
  expected=draw(self.target,0);self.assertEqual(events[0].payload[-16:],struct.pack('>IiIi',0,0,1,expected))
  p=payload(self.target['uid'],{0:self.stone['uid'],1:self.stone['uid']});events=socket(self.path,1001,p,'full',lambda n:9999,session_id='preview')
  expected=draw(self.target,9999);self.assertEqual(events[0].payload[-20:],struct.pack('>IiIii',0,0,2,expected,expected))
  self.assertEqual(socket(self.path,1001,p,'full',lambda n:7,session_id='preview')[0].payload,events[0].payload)
 def test_retry_keeps_newer_options_and_never_rolls_or_pays_again(self):
  p=payload(self.target['uid'],{0:self.stone['uid']})
  socket(self.path,1001,p,'once',lambda n:0,session_id='t');socket(self.path,1001,p,'twice',lambda n:9999,session_id='t');before=self.dump()
  socket(self.path,1001,p,'once',lambda n:self.fail('Redraw'),session_id='t');self.assertEqual(self.dump(),before)
  newer=draw(self.target,9999)
  socket_apply(self.path,1001,apply_payload(self.target['uid'],{0:newer}),'once-apply',session_id='t')
  self.assertEqual(self.target_now()['option_groups']['0'][0],newer)
 def test_failed_encoder_random_material_or_money_rolls_back_everything(self):
  p=payload(self.target['uid'],{0:self.stone['uid']});before=self.dump()
  for roll in (-1,10000,True):
   with self.assertRaises(ValueError):socket(self.path,1001,p,'random',lambda n:roll,session_id='t')
   self.assertEqual(self.dump(),before)
  with patch('els_server.storage.sage_sockets.acknowledgement',side_effect=ValueError('wire')):
   with self.assertRaises(ValueError):socket(self.path,1001,p,'wire',lambda n:0,session_id='t')
  self.assertEqual(self.dump(),before)
  for owner,wire in ((self.other,p),(1001,payload(self.target['uid'],{2:self.stone['uid']})),(1001,payload(self.target['uid'],{0:self.gear['uid']}))):
   with self.assertRaises(ValueError):socket(self.path,owner,wire,'reject',session_id='t')
   self.assertEqual(self.dump(),before)
  with closing(sqlite3.connect(self.path)) as db,db:db.execute('UPDATE reward_balances SET ed=0 WHERE uid=1001')
  before=self.dump()
  with self.assertRaises(ValueError):socket(self.path,1001,p,'money',session_id='t')
  self.assertEqual(self.dump(),before)
 def test_duplicate_concurrent_request_once(self):
  p=payload(self.target['uid'],{0:self.stone['uid']});before=self.money();cost=fee(self.target)
  with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:socket(self.path,1001,p,'same',lambda n:0,session_id='t'),range(2)))
  self.assertEqual(self.money(),before-cost);self.assertEqual(next(i['count'] for i in self.items() if i['uid']==self.stone['uid']),7)
 def test_bank_move_and_other_character_shared_withdraw_preserve_all_options(self):
  socket(self.path,1001,payload(self.target['uid'],{1:self.stone['uid']}),'roll',lambda n:9999,session_id='t')
  socket_apply(self.path,1001,apply_payload(self.target['uid'],{1:draw(self.target,9999)}),'roll-apply',session_id='t')
  item=self.target_now()
  transfer(self.path,1001,bank_payload((item['group'],item['slot']),(8,0),item),'deposit')
  self.assertEqual(snapshot(self.path,1001)['bank_items'][0]['item']['option_groups'],item['option_groups'])
  transfer(self.path,1001,bank_payload((8,0),(item['group'],item['slot']),item),'withdraw')
  transfer(self.path,1001,bank_payload((item['group'],item['slot']),(16,0),item),'shared')
  transfer(self.path,self.other,bank_payload((16,0),(1,0),item),'other-withdraw')
  with closing(sqlite3.connect(self.path)) as db:
   from els_server.storage.inventory_state import load_items
   self.assertEqual(load_items(db,self.other)[0]['option_groups'],item['option_groups']);self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
 def test_probabilities_slots_combined_body_and_validation(self):
  self.assertEqual(capacity(self.target['template']),2)
  for rows in catalog()['distributions'].values():
   self.assertEqual(sum(r['weight'] for r in rows),10000)
  i=dict(self.target,attributes=[1,0,0,0],enhancement=3,expires_at=2200000000,lock_until=2100000000,option_groups={'0':[draw(self.target,0),0]})
  self.assertGreater(len(item_body(i)),304)
  for groups in ({'0':[0]},{'0':[1,0]},{'1':[0,0]},{'0':[True,0]}):
   with self.assertRaises(ValueError):validate_item(dict(self.target,option_groups=groups))
 def test_locked_expired_and_malformed_modes(self):
  from els_server.storage.item_locks import assign
  with closing(sqlite3.connect(self.path)) as db,db:db.execute('BEGIN IMMEDIATE');assign(db,1001,self.target['uid'],2200000000)
  p=payload(self.target['uid'],{0:self.stone['uid']});before=self.dump()
  with self.assertRaises(ValueError):socket(self.path,1001,p,'locked',session_id='t')
  self.assertEqual(self.dump(),before)
  for wire in (p[:-1],p+b'\0',payload(0,{0:1}),payload(self.target['uid'],{0:1},a=1),payload(self.target['uid'],{0:1},b=1)):
   with self.assertRaises(ValueError):request(wire)
 def test_session_routes_success_and_failure(self):
  s=LocalSession(self.account,enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True)
  s.role='game';s.phase='town_ready';e=Event(0x202,kind=0x1c4,payload=payload(self.target['uid'],{0:self.stone['uid']}))
  # The routed 0x1C4 draws from the real RNG, so the confirmed values must be the
  # staged ones: Apply refuses anything the preview did not generate.
  self.assertEqual(s.handle(e,1)[0].kind,0x1c5);self.assertNotIn('option_groups',self.target_now())
  with closing(sqlite3.connect(self.path)) as db:
   candidate,slots=(json.loads(v) for v in db.execute('select candidate_json,slots_json from equipment_socket_pending').fetchone())
  s.handle(Event(0x202,kind=0x8b1,payload=apply_payload(self.target['uid'],{k:candidate[k] for k in slots})),2)
  self.assertEqual(self.target_now()['option_groups'],{'0':candidate})
  s.phase='dungeon_active';self.assertEqual(struct.unpack_from('>i',s.handle(e,3)[0].payload)[0],-1)
if __name__=='__main__':unittest.main()
