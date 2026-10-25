"""Approved unit15 native alternate groups; no network, client or live saves."""
import hashlib,json,sqlite3,struct,unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from tests import test_regional_boss_cubes_legacy as legacy
open_cube=legacy.open_cube
from tests.test_fixed_cubes import payload
from els_server.domain import regional_boss_cubes_legacy as rules
from els_server.storage.regional_boss_cube_source import _OwnedCubeSource
from els_server.storage.inventory_state import grant_items
from els_server.storage.item_instances import remove


class LithiaRegionalCubeTests(unittest.TestCase):
 grant=legacy.LegacyRegionalCubeTests.grant;items=legacy.LegacyRegionalCubeTests.items
 dump=legacy.LegacyRegionalCubeTests.dump;money=legacy.LegacyRegionalCubeTests.money
 clear_rewards=legacy.LegacyRegionalCubeTests.clear_rewards;plan=legacy.LegacyRegionalCubeTests.plan
 session=legacy.LegacyRegionalCubeTests.session
 def setUp(self):
  legacy.LegacyRegionalCubeTests.setUp(self)
  with closing(sqlite3.connect(self.path))as db,db:
   db.execute('UPDATE characters SET unit_type=15,unit_class=205 WHERE uid=1001')

 def test_all15_native_unit_branches_and_primary_data_unchanged(self):
  from els_server.storage.characters import BASE_CLASSES
  self.assertEqual(hashlib.sha256(rules.DATA_PATH.read_bytes()).hexdigest(),'28100c20b5171d1d0720904579338a7ffaa36934fd861bafdeeaa95dc4d04947')
  for unit,base in BASE_CLASSES.items():
   for row in rules.catalog().values():
    group=rules.native_group(row,unit,base);pool=rules.pool_for(row,unit,base)
    self.assertEqual(group,row['alternate_group']if unit==15 else row['primary_group'])
    self.assertEqual(pool['entries'],row['entries'])
    if unit==15:
     self.assertIsNot(pool['entries'],row['entries'])
     self.assertEqual(pool['resolved_group'],row['alternate_group'])
     self.assertIn('user-approved',pool['local_policy'])
    else:self.assertIs(pool,row)
   self.clear_rewards()
   with closing(sqlite3.connect(self.path))as db,db:
    db.execute('UPDATE characters SET unit_type=?,unit_class=? WHERE uid=1001',(unit,base))
   box=self.grant(130159)
   open_cube(self.path,1001,130159,payload(box['uid']),'all15-'+str(unit),lambda n:0)
   self.assertNotIn(box['uid'],{i['uid']for i in self.items()})
  with self.assertRaises(ValueError):rules.pool_for(rules.catalog()[130159],15,1)
  with self.assertRaises(ValueError):rules.pool_for(rules.catalog()[130159],16,205)

 def test_every86_alternate_result_both_weight_edges_in_actual_SQL(self):
  for template,row in rules.catalog().items():
   pool=rules.pool_for(row,15,205);start=0
   for entry in pool['entries']:
    for edge in(start,start+entry['weight']-1):
     self.clear_rewards();item=self.grant(template);money=self.money()
     events=open_cube(self.path,1001,template,payload(item['uid']),str(template)+'-'+str(edge),lambda n:edge)
     ack=next(e for e in events if e.kind==0x197)
     self.assertEqual(struct.unpack_from('>ii',ack.payload,16),(entry['template'],1))
     self.assertNotIn(item['uid'],{i['uid']for i in self.items()})
     self.assertEqual(sum(i['count']for i in self.items()if i['template']==entry['template']),1)
     self.assertEqual(self.money(),money)
    start+=entry['weight']
   self.assertEqual(start,10000)
   self.clear_rewards()

 def test_missing_or_disabled_alternate_contract_never_falls_back(self):
  item=self.grant(130159);before=self.dump()
  with patch.object(rules,'LITHIA_ALTERNATE_ENABLED',False):
   with self.assertRaises(ValueError):open_cube(self.path,1001,130159,payload(item['uid']),'closed',lambda n:self.fail('Closed alternate drew'))
   self.assertIs(rules.pool_for(rules.catalog()[130159],1,1),rules.catalog()[130159])
  with patch.object(rules,'LITHIA_DATA_PATH',Path(self.tmp.name)/'absent.json'):
   rules._lithia_data.cache_clear()
   try:
    with self.assertRaises(ValueError):open_cube(self.path,1001,130159,payload(item['uid']),'missing',lambda n:self.fail('Missing alternate drew'))
   finally:rules._lithia_data.cache_clear()
  self.assertEqual(self.dump(),before)

 def test_private_source_binds_original_character_branch_through_factory(self):
  item=self.grant(130159);entry=rules.pool_for(rules.catalog()[130159],15,205)['entries'][0]
  before=self.dump()
  with closing(sqlite3.connect(self.path))as db:
   db.execute('BEGIN IMMEDIATE');source=_OwnedCubeSource(db,1001,item,entry)
   self.assertEqual(source.native_group,60353)
   remove(db,1001,item);source.debit_complete()
   db.execute('UPDATE characters SET unit_type=1,unit_class=1 WHERE uid=1001')
   with self.assertRaises(ValueError):grant_items(db,self.plan(entry['template']),1001,regional_cube_source=source)
   db.rollback()
  self.assertEqual(self.dump(),before)

 def test_independent_policy_requires_approval_identity_and_exact_group_values(self):
  import copy
  original=json.loads(rules.LITHIA_DATA_PATH.read_bytes())
  item=self.grant(130159);before=self.dump()
  for case in ('unapproved','authority','group','quantity'):
   candidate=copy.deepcopy(original)
   if case=='unapproved':candidate['approved']=False
   if case=='authority':candidate['authorization_sha256']='0'*64
   if case=='group':candidate['groups'][0]['native_group']=60343
   if case=='quantity':candidate['groups'][0]['entries'][0]['quantity']=2
   raw=json.dumps(candidate,ensure_ascii=False).encode('utf-8');path=Path(self.tmp.name)/('invalid-'+case+'.json');path.write_bytes(raw)
   with patch.object(rules,'LITHIA_DATA_PATH',path),patch.object(rules,'LITHIA_DATA_SHA',hashlib.sha256(raw).hexdigest()):
    rules._lithia_data.cache_clear()
    try:
     with self.assertRaises(ValueError):
      open_cube(self.path,1001,130159,payload(item['uid']),'invalid-'+case,lambda n:self.fail('Unqualified policy drew'))
    finally:rules._lithia_data.cache_clear()
   self.assertEqual(self.dump(),before)

 def test_concurrent_duplicate_and_cold_retry_do_not_redraw(self):
  item=self.grant(162020,2);body=payload(item['uid']);rolls=[]
  def rng(n):rolls.append(n);return 9999
  def use():return open_cube(self.path,1001,162020,body,'lithia-concurrent',rng)
  with ThreadPoolExecutor(max_workers=2)as executor:answers=list(executor.map(lambda _:use(),range(2)))
  self.assertEqual(rolls,[10000]);self.assertEqual(next(i['count']for i in self.items()if i['uid']==item['uid']),1)
  before=self.dump()
  answer=open_cube(self.path,1001,162020,body,'lithia-concurrent',lambda n:self.fail('Cold retry drew'))
  self.assertEqual(self.dump(),before);self.assertEqual(struct.unpack_from('>I',answer[-1].payload,12)[0],0)

 # Same real failure paths now run with an actual unit15 owner and alternate source.
 test_expiry_lock_capacity_mode_and_preview_rollback=legacy.LegacyRegionalCubeTests.test_expiration_lock_full_bag_invalid_mode_and_wrong_preview_roll_back
 test_complete_reply_encode_and_final_actor_failure_rollback=legacy.LegacyRegionalCubeTests.test_all_receipt_encoding_and_prepare_failures_rollback
 test_required_owner_and_replay_preencoding=legacy.LegacyRegionalCubeTests.test_required_account_actor_and_replay_preencoding
 test_forged_and_mixed_capabilities_rejected=legacy.LegacyRegionalCubeTests.test_forged_mapping_and_all_mixed_sources_are_rejected
 test_foreign_owner_and_factory_result_failures_rollback=legacy.LegacyRegionalCubeTests.test_failure_and_foreign_owner_rollback


if __name__=='__main__':unittest.main()
