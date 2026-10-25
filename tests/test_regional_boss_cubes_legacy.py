"""Legacy class-independent regional cubes: disclosed weights, atomic rewards, retries."""
import sqlite3,struct,unittest
from contextlib import closing
from unittest.mock import patch
from tests import test_npc_sale as fixture
from tests.test_fixed_cubes import payload
from els_server.domain.cubes import catalog as shared_catalog
from els_server.domain.local_session import LocalSession
from els_server.domain.regional_boss_cubes import draw
from els_server.domain.regional_boss_cubes_legacy import catalog
from els_server.protocol.protocol_codec import Event
from els_server.storage.fixed_cubes import open_cube


class LegacyRegionalCubeTests(unittest.TestCase):
 setUp=fixture.SaleTests.setUp;grant=fixture.SaleTests.grant;items=fixture.SaleTests.items;dump=fixture.SaleTests.dump;money=fixture.SaleTests.money
 def clear_rewards(self):
  # The exhaustive sweep opens every reward of every cube; free the consumable
  # bag between draws so a later iteration cannot fail on capacity.
  with closing(sqlite3.connect(self.path)) as db,db:db.execute("DELETE FROM inventory_items WHERE bag_group=2")
 def test_membership_weights_and_paired_group(self):
  rows=catalog()
  self.assertEqual(len(rows),10);self.assertEqual(sum(len(r['entries']) for r in rows.values()),86)
  for template,row in rows.items():
   shared=shared_catalog()[template]
   self.assertEqual({key:shared[key] for key in row},dict(row))
   self.assertTrue(row['random']);self.assertEqual(row['selection_count'],0)
   self.assertEqual(row['grant_source'],'regional_boss_cube')
   self.assertEqual(row['alternate_group']-row['primary_group'],10)
   self.assertEqual(sum(e['weight'] for e in row['entries']),10000)
   start=0
   for entry in row['entries']:
    self.assertEqual(draw(row,start),entry);self.assertEqual(draw(row,start+entry['weight']-1),entry)
    start+=entry['weight']
   for roll in (-1,10000):
    with self.assertRaises(ValueError):draw(row,roll)
 def test_every_disclosed_reward_opens_exactly_once(self):
  for template,row in catalog().items():
   start=0
   for entry in row['entries']:
    self.clear_rewards()
    item=self.grant(template);money=self.money()
    events=open_cube(self.path,1001,template,payload(item['uid']),'reward-'+str(entry['template']),lambda n:start)
    self.assertEqual([e.kind for e in events],[0xad8,0x197])
    self.assertEqual(struct.unpack_from('>i',events[-1].payload)[0],0)
    self.assertEqual(struct.unpack_from('>I',events[-1].payload,12)[0],1)
    self.assertEqual(struct.unpack_from('>ii',events[-1].payload,16),(entry['template'],entry['quantity']))
    self.assertNotIn(item['uid'],{i['uid'] for i in self.items()})
    reward=next(i for i in self.items() if i['template']==entry['template'])
    self.assertEqual((reward['group'],reward['count']),(2,1))
    self.assertEqual(self.money(),money)
    start+=entry['weight']
   self.clear_rewards()
 def test_retry_after_exhaustion_does_not_redraw_or_repeat_popup(self):
  item=self.grant(160662);body=payload(item['uid'])
  open_cube(self.path,1001,160662,body,'legacy-retry',lambda n:0);before=self.dump()
  answer=open_cube(self.path,1001,160662,body,'legacy-retry',lambda n:self.fail('Redraw'))
  self.assertEqual(self.dump(),before);self.assertEqual(answer[-1].kind,0x197)
  self.assertEqual(struct.unpack_from('>I',answer[-1].payload,12)[0],0)
 def test_failure_and_foreign_owner_rollback(self):
  item=self.grant(162020);body=payload(item['uid']);before=self.dump()
  for name in ('els_server.storage.fixed_cubes.result','els_server.storage.fixed_cubes.grant_items'):
   with patch(name,side_effect=ValueError('fail')):
    with self.assertRaises(ValueError):open_cube(self.path,1001,162020,body,'fail-'+name,lambda n:0)
   self.assertEqual(self.dump(),before)
  with self.assertRaises(ValueError):open_cube(self.path,self.other,162020,body,'foreign',lambda n:0)
  self.assertEqual(self.dump(),before)
 def test_owned_preview_and_use_are_routed_without_ice_mode(self):
  template=130161;row=catalog()[template];item=self.grant(template)
  s=LocalSession(self.account,enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True)
  s.role='game';s.phase='town_ready'
  reply=s.handle(Event(0x202,kind=0x559,payload=struct.pack('>iIBB',template,0,0,0)),1)
  self.assertEqual(reply[0].kind,0x55a)
  self.assertEqual(struct.unpack_from('>i',reply[0].payload)[0],0)
  self.assertEqual(struct.unpack_from('>i',reply[0].payload,4)[0],template)
  self.assertEqual(struct.unpack_from('>I',reply[0].payload,17)[0],len(row['entries']))
  answer=s.handle(Event(0x202,kind=0x196,payload=payload(item['uid'])),2)
  self.assertEqual(answer[-1].kind,0x197)
  self.assertEqual(struct.unpack_from('>i',answer[-1].payload)[0],0)
  self.assertNotIn(item['uid'],{i['uid'] for i in self.items()})
  self.assertTrue(any(i['group']==2 for i in self.items()))


if __name__=='__main__':unittest.main()
