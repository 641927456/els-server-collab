"""Actual kill/clear SQL writers: leveling, cap, replay and atomic failure."""
import json,sqlite3,struct,sys,tempfile,unittest,uuid
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import importlib.util,os
ROOT=Path(__file__).resolve().parents[1]
RUNTIME=os.environ.get('ELS_MAINLINE_TEST_RUNTIME')
if not RUNTIME:raise unittest.SkipTest('Set ELS_MAINLINE_TEST_RUNTIME to the pinned complete server runtime')
OUT=Path(os.environ['ELS_MAINLINE_TEST_WORK']).resolve()
(OUT/'qa-temp').mkdir(parents=True,exist_ok=True);tempfile.tempdir=str(OUT/'qa-temp')
sys.dont_write_bytecode=True;sys.path.insert(0,str(Path(RUNTIME).resolve()))
# Run the archived delivery implementations with the complete pinned runtime dependencies.
# Runtime resources are external assets; only the two edited source modules
# are substituted, preserving the differences of this Git branch.
for module,relative in (
 ('els_server.domain.formal_pve_economy','els_server/domain/formal_pve_economy.py'),
 ('els_server.storage.reward_state','els_server/storage/reward_state.py')):
    import importlib
    parent,name=module.rsplit('.',1);package=importlib.import_module(parent)
    spec=importlib.util.spec_from_file_location(module,ROOT/'references/mainline-leveling-exp20-20261031-v1/source/common'/relative)
    value=importlib.util.module_from_spec(spec);sys.modules[module]=value
    spec.loader.exec_module(value);setattr(package,name,value)
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.reward_state import RewardState,RewardConflict
from els_server.storage import legacy_pve_exp as kills,resonance_state as er
from els_server.domain import legacy_pve_exp as old,formal_pve_economy as rules
from els_server.domain.dungeon_routes import DungeonRun
from els_server.domain.dungeon_clear import reward_clear_notice
from els_server.game_data import client_data

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=OUT/'qa-temp');self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'own.sqlite3'
        self.account=LocalAccount(LocalState(self.path));self.account.enable_characters();self.account.enable_rewards();self.account.enable_inventory()
        self.store=self.account.reward_store
        self.run=DungeonRun(30000,str(uuid.uuid4()))
        self.session=SimpleNamespace(account=self.account,reward_run_id=self.run.run_id,dungeon_run=self.run)

    def sql(self,sql,args=()):
        with closing(sqlite3.connect(self.path))as db,db:return db.execute(sql,args).fetchall()

    def dump(self):
        with closing(sqlite3.connect(self.path))as db:return list(db.iterdump())

    def at(self,xp,unlock=False):
        level=client_data().level_for_experience(xp)
        self.sql('UPDATE characters SET level=?WHERE uid=1001',(level,))
        self.sql('UPDATE reward_balances SET experience=?WHERE uid=1001',(xp,))
        if unlock:
            with closing(sqlite3.connect(self.path))as db,db:
                db.execute('BEGIN IMMEDIATE');er.ensure(db);db.execute('INSERT INTO account_resonance VALUES(1,1,0,0)')

    def kill(self):
        npc=next(n for n in self.run.current['npcs']if old.eligible(n))
        context=old.identity(self.session,npc)
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE')
            return kills.commit(db,self.store,context,b'owned exact admitted enemy',1001)

    def clear(self,builder=None,proof=b'owned complete clear'):
        with closing(sqlite3.connect(self.path))as db:
            basis=kills.run_total(db,1001,self.run.run_id,clear_basis=True)
        def encode(balances,best,economy):
            return reward_clear_notice(economy['ed'],economy['experience'],1001,map_id=30000).payload
        return self.store.grant(self.run.run_id,proof,0,rules.clear_bonus(basis),builder or encode,
            dungeon_clear=(30000,30),title_economy='clear',experience_limit=old.experience_limit(),resonance_source='clear')

    def test_ordinary20x_total_cold_replay_and_conflict(self):
        self.assertEqual(self.kill()['experience'],18)
        result=self.clear();self.assertEqual(result['balances']['experience'],460)
        self.assertEqual(struct.unpack_from('>Q',result['response'],84)[0],442)
        self.assertEqual(result['title_economy']['leveling_experience'],dict(multiplier=20,kill_experience=18,clear_experience=5))
        self.store=RewardState(self.path,account_id=1)
        replay=self.clear(lambda *args:(_ for _ in()).throw(AssertionError('re-encoded replay')))
        self.assertTrue(replay['replayed']);self.assertEqual(replay['response'],result['response'])
        self.assertEqual(self.store.balances()['experience'],460)
        with self.assertRaises(RewardConflict):self.clear(proof=b'conflict')

    def test_cap99_replay_after_level_change_no_ERP_spill(self):
        self.at(old.experience_limit()-100,unlock=True);self.kill();result=self.clear()
        self.assertEqual(result['balances']['experience'],old.experience_limit())
        self.assertEqual(self.sql('SELECT level FROM characters WHERE uid=1001'),[(99,)])
        self.assertEqual(struct.unpack_from('>Q',result['response'],84)[0],82)
        self.assertEqual(self.sql('SELECT experience FROM account_resonance'),[(0,)])
        self.assertEqual(self.clear()['response'],result['response'])

    def test_already99_ERP10x_unchanged(self):
        self.at(old.experience_limit(),unlock=True);self.assertEqual(self.kill()['experience'],180)
        result=self.clear();self.assertEqual(result['resonance_award']['effective'],50)
        self.assertNotIn('leveling_experience',result['title_economy'])
        self.assertEqual(self.sql('SELECT experience FROM account_resonance'),[(230,)])
        self.assertEqual(self.store.balances()['experience'],old.experience_limit())

    def test_encoder_and_receipt_failure_rollback(self):
        self.at(old.experience_limit()-100);self.kill();before=self.dump()
        with self.assertRaisesRegex(RuntimeError,'encoder'):
            self.clear(lambda *args:(_ for _ in()).throw(RuntimeError('encoder')))
        self.assertEqual(self.dump(),before)
        self.sql("CREATE TRIGGER fail_clear BEFORE INSERT ON reward_receipts BEGIN SELECT RAISE(ABORT,'clear receipt');END")
        before=self.dump()
        with self.assertRaises(sqlite3.IntegrityError):self.clear()
        self.assertEqual(self.dump(),before)

    def test_old_clear_receipt_keeps_original_amount(self):
        self.kill()
        with patch.object(rules,'leveling_multiplier',return_value=1):first=self.clear()
        self.assertEqual(first['balances']['experience'],23)
        self.assertEqual(self.clear()['response'],first['response'])
        self.assertEqual(self.store.balances()['experience'],23)

    def test_zero_kills_no_free_level_and_special_maps_excluded(self):
        self.assertEqual(self.clear()['balances']['experience'],0)
        for mid in (34130,33031,35720):self.assertEqual(rules.leveling_multiplier(mid),1)
        for mid in (30000,30092,34200,34580,35250):self.assertEqual(rules.leveling_multiplier(mid),20)

if __name__=='__main__':unittest.main(verbosity=2)
