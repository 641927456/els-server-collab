"""Real reward writers: ordinary2x, ERP10x, clear basis, replay and rollback."""
import source
from source import HERE,CHANNEL
import json,sqlite3,struct,tempfile,unittest,uuid
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.reward_state import RewardState,RewardConflict
from els_server.storage import legacy_pve_exp as kills,resonance_state as er
from els_server.domain import legacy_pve_exp as old,formal_pve_economy as rules,hot_time
from els_server.domain.dungeon_routes import DungeonRun
from els_server.domain.dungeon_clear import reward_clear_notice
from els_server.game_data import client_data

class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=HERE,prefix='owned-economy-');self.addCleanup(self.tmp.cleanup)
  self.path=Path(self.tmp.name)/'own.sqlite3';self.account=LocalAccount(LocalState(self.path))
  self.account.enable_characters();self.account.enable_rewards();self.account.enable_inventory();self.store=self.account.reward_store
  self.run=DungeonRun(30000,str(uuid.uuid4()));self.session=SimpleNamespace(account=self.account,reward_run_id=self.run.run_id,dungeon_run=self.run)
 def sql(self,sql,args=()):
  with closing(sqlite3.connect(self.path))as db,db:return db.execute(sql,args).fetchall()
 def dump(self):
  with closing(sqlite3.connect(self.path))as db:return list(db.iterdump())
 def at(self,xp,unlock=False):
  self.sql('UPDATE characters SET level=?WHERE uid=1001',(client_data().level_for_experience(xp),))
  self.sql('UPDATE reward_balances SET experience=?WHERE uid=1001',(xp,))
  if unlock:
   with closing(sqlite3.connect(self.path))as db,db:
    db.execute('BEGIN IMMEDIATE');er.ensure(db);db.execute('INSERT INTO account_resonance VALUES(1,1,0,0)')
 def kill(self):
  npc=next(n for n in self.run.current['npcs']if old.eligible(n));context=old.identity(self.session,npc)
  with closing(sqlite3.connect(self.path))as db,db:
   db.execute('BEGIN IMMEDIATE');return kills.commit(db,self.store,context,b'owned exact admitted enemy',1001)
 def clear(self,builder=None,proof=b'owned complete clear'):
  with closing(sqlite3.connect(self.path))as db:basis=kills.run_total(db,1001,self.run.run_id,clear_basis=True)
  def encode(balances,best,economy):return reward_clear_notice(economy['ed'],economy['experience'],1001,map_id=30000).payload
  return self.store.grant(self.run.run_id,proof,0,rules.clear_bonus(basis),builder or encode,dungeon_clear=(30000,30),title_economy='clear',experience_limit=old.experience_limit(),resonance_source='clear')
 def test_ordinary_double_no_clear_compounding_cold_replay(self):
  self.assertEqual(self.kill()['experience'],36)
  with closing(sqlite3.connect(self.path))as db:self.assertEqual(kills.run_total(db,1001,self.run.run_id,clear_basis=True),18)
  result=self.clear();self.assertEqual(result['balances']['experience'],920)
  self.assertEqual(struct.unpack_from('>Q',result['response'],84)[0],884)
  self.store=RewardState(self.path,account_id=1);replay=self.clear(lambda *a:(_ for _ in()).throw(AssertionError('re-encoded replay')))
  self.assertTrue(replay['replayed']);self.assertEqual(replay['response'],result['response']);self.assertEqual(self.store.balances()['experience'],920)
  with self.assertRaises(RewardConflict):self.clear(proof=b'conflict')
 def test_erp_ten_unchanged(self):
  self.at(old.experience_limit(),True);self.assertEqual(self.kill()['experience'],180)
  result=self.clear();self.assertEqual(result['resonance_award']['effective'],50)
  self.assertEqual(self.sql('SELECT experience FROM account_resonance'),[(230,)])
  self.assertEqual(self.store.balances()['experience'],old.experience_limit())
 def test_cap_and_no_ordinary_spill_to_erp(self):
  self.at(old.experience_limit()-7,True);self.assertEqual(self.kill()['experience'],7)
  self.assertEqual(self.store.balances()['experience'],old.experience_limit());self.assertEqual(er.state(self.path,1001,1)['experience'],0)
  self.run.visits+=1;self.assertEqual(self.kill()['experience'],180)
 def test_failure_rolls_back_ordinary_and_erp(self):
  self.kill();before=self.dump()
  with self.assertRaisesRegex(RuntimeError,'encoder'):self.clear(lambda *a:(_ for _ in()).throw(RuntimeError('encoder')))
  self.assertEqual(self.dump(),before)
  self.sql("CREATE TRIGGER fail_clear BEFORE INSERT ON reward_receipts BEGIN SELECT RAISE(ABORT,'clear receipt');END")
  before=self.dump()
  with self.assertRaises(sqlite3.IntegrityError):self.clear()
  self.assertEqual(self.dump(),before)
  self.sql('DROP TRIGGER fail_clear');self.at(old.experience_limit(),True);before=self.dump()
  with self.assertRaisesRegex(RuntimeError,'encoder'):self.clear(lambda *a:(_ for _ in()).throw(RuntimeError('encoder')))
  self.assertEqual(self.dump(),before)
 def test_existing_clear_and_kill_receipts_not_topped_up(self):
  with patch.object(hot_time,'ordinary_multiplier',return_value=1):
   self.assertEqual(self.kill()['experience'],18);first=self.clear();self.assertEqual(first['balances']['experience'],460)
  # Exercise an actual pre-feature receipt without this JSON field.
  with closing(sqlite3.connect(self.path))as db,db:
   for operation,raw in db.execute('SELECT run_id,grant_json FROM reward_receipts').fetchall():
    value=json.loads(raw);value.pop('hot_time_ordinary_multiplier');db.execute('UPDATE reward_receipts SET grant_json=?WHERE run_id=?',(json.dumps(value,sort_keys=True,separators=(',',':')),operation))
  before=self.dump();self.assertTrue(self.kill()['replayed']);self.assertEqual(self.clear()['response'],first['response']);self.assertEqual(self.dump(),before)
 def test_generic_reward_and_ownership_keep_existing_behavior(self):
  result=self.store.grant(str(uuid.uuid4()),b'unrelated reward',7,100,lambda b:b'ack')
  self.assertEqual(result['balances']['experience'],100);self.assertEqual(result['balances']['ed'],7)
  wrong=RewardState(self.path,1001,account_id=2);before=self.dump()
  with self.assertRaises(ValueError):wrong.grant(str(uuid.uuid4()),b'foreign owner',0,100,lambda b:b'ack',resonance_source='kill')
  self.assertEqual(self.dump(),before)
 def test_actual_activity_records_match_authoritative_rates(self):
  records=hot_time.records();self.assertEqual([(r.category_80,r.float_84,r.bool_a0)for r in records],[(6,0.,False),(3,1.,False),(3,9.,True)])

if __name__=='__main__':
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 (HERE/f'qa-business-{CHANNEL}.json').write_text(json.dumps(dict(ok=result.wasSuccessful(),tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),temporary_saves_removed=not any(HERE.glob('owned-economy-*')),natural_GUI=False),indent=2)+'\n')
 raise SystemExit(0 if result.wasSuccessful()else 1)
