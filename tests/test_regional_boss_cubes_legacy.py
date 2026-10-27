"""Existing owned cubes: exact native primary branch, atomic rewards and retries."""
import asyncio,inspect,sqlite3,struct,time,unittest
from contextlib import closing,nullcontext
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from tests import test_npc_sale as fixture
from tests.test_fixed_cubes import payload
from els_server.domain.cubes import catalog as shared_catalog
from els_server.domain.local_session import LocalSession
from els_server.domain.regional_boss_cubes import draw
from els_server.domain.regional_boss_cubes_legacy import catalog
from els_server.protocol.protocol_codec import Event
from els_server.storage.fixed_cubes import open_cube as storage_open_cube
from els_server.storage.inventory_state import grant_items,validate_plan,load_items
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.domain.acquisition_policy import can_acquire
from els_server.storage.regional_boss_cube_source import _OwnedCubeSource


def open_cube(*args,**kwargs):
 # Storage tests explicitly supply a private owner and inert private actor.
 # Native session tests below use the real Application.session authority path.
 kwargs.setdefault('account_id',1);kwargs.setdefault('prepare',lambda db:None)
 return storage_open_cube(*args,**kwargs)


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
 def test_partial_stack_and_concurrent_duplicate_authorize_only_one_draw(self):
  item=self.grant(130159,3);body=payload(item['uid']);rolls=[]
  def draw_once(n):rolls.append(n);return 0
  def use():return open_cube(self.path,1001,130159,body,'concurrent-partial',draw_once)
  with ThreadPoolExecutor(max_workers=2) as pool:
   answers=list(pool.map(lambda _:use(),range(2)))
  self.assertEqual(rolls,[10000])
  self.assertEqual(next(i['count'] for i in self.items() if i['uid']==item['uid']),2)
  self.assertEqual(sum(i['count'] for i in self.items() if i['template']==30163),1)
  self.assertEqual(sorted(struct.unpack_from('>I',a[-1].payload,12)[0] for a in answers),[0,1])
  before=self.dump()
  with self.assertRaises(ValueError):
   open_cube(self.path,1001,130159,payload(item['uid'],option=1),'concurrent-partial',draw_once)
  self.assertEqual(self.dump(),before)
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
  s=self.session()
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

 def session(self):
  from els_server.application import Application
  from els_server.config import ServerConfig
  app=Application(ServerConfig(state_file=self.path,log_dir=self.path.parent/'logs'))
  self.addCleanup(app.executor.shutdown,wait=True)
  app.account=self.account.root
  s=asyncio.run(app.session())
  s.role='game';s.phase='town_ready';s.active_map=20013;s.completed.update((0x28,0x225,0x227))
  return s

 def test_lithia_approved_alternate_native_preview_and_use(self):
  from els_server.domain.regional_boss_cubes_legacy import pool_for
  with closing(sqlite3.connect(self.path)) as db,db:
   db.execute('UPDATE characters SET unit_type=15,unit_class=205 WHERE uid=1001')
  row=pool_for(catalog()[130159],15,205);self.assertEqual(row['resolved_group'],60353)
  item=self.grant(130159);s=self.session()
  reply=s.handle(Event(0x202,kind=0x559,payload=struct.pack('>iIBB',130159,0,0,0)),1)
  self.assertEqual(struct.unpack_from('>i',reply[0].payload)[0],0)
  self.assertEqual(struct.unpack_from('>I',reply[0].payload,17)[0],len(row['entries']))
  answer=s.handle(Event(0x202,kind=0x196,payload=payload(item['uid'])),2)
  self.assertEqual(struct.unpack_from('>i',next(e for e in answer if e.kind==0x197).payload)[0],0)
  self.assertNotIn(item['uid'],{i['uid']for i in self.items()})
  self.assertEqual(sum(i['count']for i in self.items()if i['template']in{e['template']for e in row['entries']}),1)

 def test_stale_session_and_foreign_envelope_reject_native_use(self):
  item=self.grant(130159);s=self.session();before=self.dump()
  answer=s.handle(Event(0x202,kind=0x196,uid=7,payload=payload(item['uid'])),1)
  self.assertNotEqual(struct.unpack_from('>i',answer[-1].payload)[0],0)
  self.assertEqual(self.dump(),before)
  s._chip_reset_local_live=False
  answer=s.handle(Event(0x202,kind=0x196,payload=payload(item['uid'])),2)
  self.assertNotEqual(struct.unpack_from('>i',answer[-1].payload)[0],0)
  self.assertEqual(self.dump(),before)

 def plan(self,template):
  return [dict(template=template,metadata=VERIFIED_TEMPLATES[template],group=TEMPLATE_BAG_GROUPS[template],quantity=1)]

 def test_all_primary_native_unit_branches_and_advanced_class_are_accepted(self):
  from els_server.storage.characters import BASE_CLASSES
  for unit,base in BASE_CLASSES.items():
   if unit==15:continue
   self.clear_rewards()
   with closing(sqlite3.connect(self.path)) as db,db:
    db.execute('UPDATE characters SET unit_type=?,unit_class=? WHERE uid=1001',(unit,base))
   item=self.grant(130159)
   open_cube(self.path,1001,130159,payload(item['uid']),'branch-'+str(unit),lambda n:0)
   self.assertNotIn(item['uid'],{i['uid'] for i in self.items()})
  self.clear_rewards()
  with closing(sqlite3.connect(self.path)) as db,db:
   db.execute('UPDATE characters SET unit_type=1,unit_class=11 WHERE uid=1001')
  item=self.grant(130159)
  open_cube(self.path,1001,130159,payload(item['uid']),'advanced-primary',lambda n:0)
  self.assertNotIn(item['uid'],{i['uid'] for i in self.items()})

 def test_disabled_lithia_alternate_pool_refuses_all_ten_without_draw_or_debit(self):
  with patch('els_server.domain.regional_boss_cubes_legacy.LITHIA_ALTERNATE_ENABLED',False):
   with closing(sqlite3.connect(self.path)) as db,db:
    db.execute('UPDATE characters SET unit_type=15,unit_class=205 WHERE uid=1001')
   for template in catalog():
    item=self.grant(template);before=self.dump()
    with self.assertRaises(ValueError):
     open_cube(self.path,1001,template,payload(item['uid']),'unknown-'+str(template),lambda n:self.fail('Unknown pool drew'))
    self.assertEqual(self.dump(),before)

 def test_expiration_lock_full_bag_invalid_mode_and_wrong_preview_roll_back(self):
  from els_server.storage.item_expiration import assign as expire
  from els_server.storage.item_locks import assign as lock
  for kind in ('expiry','lock','full','mode','preview'):
   item=self.grant(130159)
   with closing(sqlite3.connect(self.path)) as db,db:
    db.execute('BEGIN IMMEDIATE')
    if kind=='expiry':expire(db,1001,item['uid'],int(time.time())-100)
    if kind=='lock':lock(db,1001,item['uid'],int(time.time())+1000)
   before=self.dump()
   limits={g:36 for g in(1,2,3,4,5,6,7,21,27,11)};limits[2]=0
   with patch('els_server.storage.bag_capacity.allowances',return_value=limits) if kind=='full' else nullcontext():
    with self.assertRaises(ValueError):
     open_cube(self.path,1001,130160 if kind=='preview' else 130159,
               payload(item['uid'],option=1 if kind=='mode' else 0),'refusal-'+kind,lambda n:0)
   self.assertEqual(self.dump(),before)

 def test_all_receipt_encoding_and_prepare_failures_rollback(self):
  item=self.grant(130159);before=self.dump()
  from els_server.protocol.protocol_codec import encode_event
  for failed_kind in (0xad8,0x197):
   def encode(event):
    if event.kind==failed_kind:raise ValueError('native receipt encode failure')
    return encode_event(event)
   with patch('els_server.protocol.protocol_codec.encode_event',side_effect=encode):
    with self.assertRaises(ValueError):
     open_cube(self.path,1001,130159,payload(item['uid']),'encoding-'+str(failed_kind),lambda n:0)
   self.assertEqual(self.dump(),before)
  calls=[]
  def fail_prepare(db):
   self.assertTrue(db.in_transaction);calls.append(True)
   if len(calls)==2:raise ValueError('final selected actor changed')
  with self.assertRaises(ValueError):
   open_cube(self.path,1001,130159,payload(item['uid']),'prepare-fail',lambda n:0,prepare=fail_prepare)
  self.assertEqual(self.dump(),before)
  self.assertEqual(len(calls),2)

 def test_required_account_actor_and_replay_preencoding(self):
  item=self.grant(130159);body=payload(item['uid']);before=self.dump()
  for account,prepare in ((None,None),(None,lambda db:None),(2,lambda db:None),(1,None)):
   with self.assertRaises(ValueError):
    storage_open_cube(self.path,1001,130159,body,'actor-missing',lambda n:0,account_id=account,prepare=prepare)
   self.assertEqual(self.dump(),before)
  open_cube(self.path,1001,130159,body,'actor-retry',lambda n:0);before=self.dump()
  with self.assertRaises(ValueError):
   open_cube(self.path,1001,130159,body,'actor-retry',lambda n:self.fail('Replay drew'),account_id=2)
  self.assertEqual(self.dump(),before)
  calls=[]
  def prepare(db):calls.append(db.in_transaction)
  answer=open_cube(self.path,1001,130159,body,'actor-retry',lambda n:self.fail('Replay drew'),prepare=prepare)
  self.assertEqual(calls,[True,True]);self.assertEqual(self.dump(),before)
  self.assertEqual(struct.unpack_from('>I',answer[-1].payload,12)[0],0)
  with patch('els_server.protocol.protocol_codec.encode_event',side_effect=ValueError('replay encode failure')):
   with self.assertRaises(ValueError):open_cube(self.path,1001,130159,body,'actor-retry',lambda n:self.fail('Replay drew'))
  self.assertEqual(self.dump(),before)

 def test_forged_mapping_and_all_mixed_sources_are_rejected(self):
  row=catalog()[130159];template=row['entries'][0]['template'];plan=self.plan(template)
  for fake in (row,dict(row),object(),None):
   if fake is None:
    self.assertFalse(can_acquire(template));continue
   with self.assertRaises(ValueError):can_acquire(template,regional_cube_source=fake)
   with self.assertRaises(ValueError):validate_plan(plan,regional_cube_source=fake)
   with closing(sqlite3.connect(self.path)) as db,db:
    db.execute('BEGIN IMMEDIATE')
    with self.assertRaises(ValueError):grant_items(db,plan,1001,regional_cube_source=fake)
  for name in inspect.signature(grant_items).parameters:
   if name.endswith('_source') and name!='regional_cube_source' or name in ('selected_accessory_box','chip_options'):
    before=self.dump()
    with closing(sqlite3.connect(self.path)) as db,db:
     db.execute('BEGIN IMMEDIATE')
     with self.assertRaises(ValueError):grant_items(db,plan,1001,regional_cube_source=row,**{name:object()})
    self.assertEqual(self.dump(),before)

 def test_private_source_requires_exact_debit_owner_output_and_single_use(self):
  from els_server.storage.item_instances import remove
  item=self.grant(130159);entry=catalog()[130159]['entries'][0];plan=self.plan(entry['template'])
  before=self.dump()
  with closing(sqlite3.connect(self.path)) as db:
   db.execute('BEGIN IMMEDIATE')
   with self.assertRaises(ValueError):_OwnedCubeSource(db,self.other,item,entry)
   with self.assertRaises(ValueError):_OwnedCubeSource(db,1001,item,catalog()[130160]['entries'][0])
   source=_OwnedCubeSource(db,1001,item,entry)
   with self.assertRaises(ValueError):source.debit_complete()
   remove(db,1001,item);source.debit_complete()
   with self.assertRaises(ValueError):grant_items(db,self.plan(catalog()[130160]['entries'][0]['template']),1001,regional_cube_source=source)
   with self.assertRaises(ValueError):grant_items(db,plan,self.other,regional_cube_source=source)
   grant_items(db,plan,1001,regional_cube_source=source)
   with self.assertRaises(ValueError):grant_items(db,plan,1001,regional_cube_source=source)
   db.rollback()
  self.assertEqual(self.dump(),before)

 def test_private_source_does_not_survive_transaction_boundary(self):
  from els_server.storage.item_instances import remove
  item=self.grant(130159);entry=catalog()[130159]['entries'][0];before=self.dump()
  with closing(sqlite3.connect(self.path)) as db:
   db.execute('BEGIN IMMEDIATE');source=_OwnedCubeSource(db,1001,item,entry)
   remove(db,1001,item);source.debit_complete();db.rollback();db.execute('BEGIN IMMEDIATE')
   with self.assertRaises((ValueError,sqlite3.Error)):
    grant_items(db,self.plan(entry['template']),1001,regional_cube_source=source)
   db.rollback()
  self.assertEqual(self.dump(),before)

 def test_optional_candidate_missing_does_not_disable_existing_cube_catalog(self):
  from pathlib import Path
  with patch('els_server.domain.regional_boss_cubes_legacy.DATA_PATH',Path(self.tmp.name)/'not-installed.json'):
   shared_catalog.cache_clear()
   try:
    self.assertIn(130172,shared_catalog());self.assertNotIn(130159,shared_catalog())
   finally:shared_catalog.cache_clear()


if __name__=='__main__':unittest.main()
