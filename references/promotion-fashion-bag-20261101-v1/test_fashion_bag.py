"""Controlled Application/SQL regression for job costume bag classification."""
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import json,sqlite3,struct,time,unittest
import test_box_fixture as fixture
from els_server.storage.inventory_state import InventoryState,InventoryFull,load_items
from els_server.domain.inventory_items import TEMPLATE_BAG_GROUPS,FASHION_EQUIP_SLOTS
from els_server.domain.fashion_state import move_fashion
from els_server.protocol.protocol_codec import Event,encode_event


class FashionBagTests(fixture.Boxes):
 def test_all_box_readers_match_native_ordinary_or_ice_bag(self):
  from els_server.game_data import client_data
  from els_server.domain import owned_reward_boxes,job_reward_boxes,promotion_reward_boxes
  client=client_data();ordinary=set()
  for module in (owned_reward_boxes,job_reward_boxes,promotion_reward_boxes):
   for row in module.catalog()['readers']:
    if row['group']not in(7,27):continue
    expected=27 if client.item(row['template'])['flags8']&256 else 7
    self.assertEqual(row['group'],expected,row['template'])
    self.assertEqual(TEMPLATE_BAG_GROUPS[row['template']],expected)
    self.assertIn(row['template'],FASHION_EQUIP_SLOTS)
    if expected==7:ordinary.add(row['template'])
  self.assertTrue({40120,183404}<=ordinary)
  self.assertEqual(TEMPLATE_BAG_GROUPS[81021],27)

 def open_fashion(self,t,sequence=1):
  box=self.grant(t);before={i['uid']for i in self.items()}
  event=Event(0x202,performers=(0,),kind=0x196,payload=fixture.wire(box['uid']))
  events=self.s.handle(event,sequence)
  self.assertEqual(struct.unpack_from('>i',fixture.ack(events,0x197).payload)[0],0)
  for e in events:encode_event(e)
  new=[i for i in self.items()if i['uid']not in before]
  fashion=[i for i in new if i['template']in FASHION_EQUIP_SLOTS]
  self.assertTrue(fashion,t);self.assertTrue(all(i['group']==7 for i in fashion),t)
  return box,event,fashion

 def test_app_open_equip_unwear_retry_and_cold_read(self):
  for sequence,t in enumerate((135666,135871,109999,110850,300646),200):
   with self.subTest(template=t):
    foreign=self.items(self.other);box,event,items=self.open_fashion(t,sequence)
    snapshot=self.snapshot();retry=self.s.handle(event,sequence)
    self.assertEqual(self.snapshot(),snapshot)
    self.assertEqual(struct.unpack_from('>I',fixture.ack(retry,0x197).payload,12)[0],0)
    item=items[0];slot=FASHION_EQUIP_SLOTS[item['template']]
    move_fashion(self.path,struct.pack('>BiBiB',7,item['slot'],9,slot,0),self.uid)
    # The original ordinary starter occupies the same native equipment slot.
    move_fashion(self.path,struct.pack('>BiBiB',9,slot,7,item['slot'],0),self.uid)
    self.assertEqual(next(i for i in self.items()if i['uid']==item['uid']),item)
    cold=InventoryState(self.path,self.uid).snapshot()['items']
    self.assertEqual(cold,self.items());self.assertEqual(self.items(self.other),foreign)

 def legacy_items(self):
  starter=next(i for i in self.items()if i['group']==9 and i['template']in FASHION_EQUIP_SLOTS)
  move_fashion(self.path,struct.pack('>BiBiB',9,starter['slot'],7,0,0),self.uid)
  box,event,items=self.open_fashion(135666,500)
  # Preserve exact committed receipt history from the old group27 writer.
  with closing(sqlite3.connect(self.path))as db,db:
   # An authentic ice costume in the same bag must retain its slot and UID.
   ice_uid=db.execute('SELECT next_uid FROM inventory_sequence WHERE id=1').fetchone()[0]
   db.execute('UPDATE inventory_sequence SET next_uid=? WHERE id=1',(ice_uid+1,))
   db.execute('INSERT INTO inventory_items VALUES (?,?,?,?,?,?,?)',(ice_uid,self.uid,81021,0,1,27,30))
   occupied={r[0]for r in db.execute('SELECT slot FROM inventory_items WHERE owner=? AND bag_group=7',(self.uid,))}
   collision=next(iter(occupied))
   for n,item in enumerate(items):
    db.execute('UPDATE inventory_items SET bag_group=27,slot=? WHERE uid=?',(collision+n,item['uid']))
   row=db.execute('SELECT operation_id,after_json,positions_json FROM inventory_action_receipts WHERE owner=? AND kind=?',(self.uid,0x196)).fetchone()
   # The receipt column for changed positions is part of the existing schema.
   history=json.loads(row[1]);positions=json.loads(row[2])
   old_positions={(i['group'],i['slot']):[27,collision+n]for n,i in enumerate(items)}
   for item in history:
    if item['uid']in {i['uid']for i in items}:
     item['group'],item['slot']=old_positions[(item['group'],item['slot'])]
   positions=[old_positions.get(tuple(p),p)for p in positions]
   db.execute('UPDATE inventory_action_receipts SET after_json=?,positions_json=? WHERE operation_id=?',
      (json.dumps(history),json.dumps(positions),row[0]))
  return box,event,items

 def test_existing_items_migrate_preserving_uid_children_receipts_and_replay(self):
  box,event,items=self.legacy_items()
  with closing(sqlite3.connect(self.path))as db:
   tables=[r[0]for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('inventory_items','inventory_migrations')")]
   before={name:db.execute('SELECT * FROM "'+name+'"').fetchall()for name in tables}
  foreign=self.items(self.other)
  migrated=InventoryState(self.path,self.uid).snapshot()['items']
  by_uid={i['uid']:i for i in migrated}
  self.assertEqual([(i['group'],i['slot'])for i in migrated if i['template']==81021],[(27,30)])
  for item in items:
   actual=by_uid[item['uid']]
   self.assertEqual(actual['group'],7)
   self.assertEqual({k:v for k,v in actual.items()if k!='slot'},{k:v for k,v in item.items()if k!='slot'})
  with closing(sqlite3.connect(self.path))as db:
   self.assertEqual({name:db.execute('SELECT * FROM "'+name+'"').fetchall()for name in tables},before)
   self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
  snapshot=self.snapshot();InventoryState(self.path,self.uid)
  self.assertEqual(self.snapshot(),snapshot)
  retry=self.s.handle(event,500)
  self.assertEqual(struct.unpack_from('>I',fixture.ack(retry,0x197).payload,12)[0],0)
  self.assertEqual(self.snapshot(),snapshot);self.assertEqual(self.items(self.other),foreign)

 def test_ordinary_bag_full_and_late_encoding_roll_back_open(self):
  box=self.grant(135666)
  from els_server.storage.bag_capacity import allowances
  with closing(sqlite3.connect(self.path))as db:limits=allowances(db,self.uid)
  limits[7]=0
  with patch('els_server.storage.bag_capacity.allowances',return_value=limits):
   self.reject(lambda:self.use(box,'ordinary-full'))
  with patch('els_server.protocol.protocol_codec.encode_event',side_effect=ValueError('late-codec')):
   self.reject(lambda:self.use(box,'late-codec'))

 def test_full_migration_rolls_back_and_can_resume(self):
  self.legacy_items();before=self.snapshot()
  from els_server.storage.bag_capacity import allowances
  with closing(sqlite3.connect(self.path))as db:limits=allowances(db,self.uid)
  limits[7]=2  # One item moves before the next item discovers a full target bag.
  with patch('els_server.storage.bag_capacity.allowances',return_value=limits):
   with self.assertRaises(InventoryFull):InventoryState(self.path,self.uid)
  self.assertEqual(self.snapshot(),before)
  self.assertTrue(all(i['group']!=27 for i in InventoryState(self.path,self.uid).snapshot()['items']if i['template']!=81021))


for name in vars(fixture.Boxes):
 if name.startswith('test_'):setattr(FashionBagTests,name,None)

if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(FashionBagTests)
 result=unittest.TextTestRunner(verbosity=2).run(suite)
 report=dict(ok=result.wasSuccessful(),tests=result.testsRun,errors=[s for _,s in result.errors],failures=[s for _,s in result.failures],natural_GUI=False,installed=False)
 (Path(__file__).parent/'test-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
 raise SystemExit(not result.wasSuccessful())
