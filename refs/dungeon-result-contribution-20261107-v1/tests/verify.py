"""Numerical rules, original codecs and atomic durable bonus/replay checks."""
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import patch
from dataclasses import replace
from contextlib import closing
import importlib.util,json,os,sqlite3,struct,sys,tempfile,unittest,uuid

HERE=Path(__file__).resolve().parent
R=Path(os.environ.get('ELS_WORKSPACE','G:/els'));RUNTIME=Path(os.environ['ELS_STATS_CANDIDATE'])
ARTIFACTS=Path(os.environ.get('ELS_TEST_ARTIFACTS',str(R/'analysis/dungeon-result-contribution-tests-v1')))
ARTIFACTS.mkdir(parents=True,exist_ok=True)
sys.dont_write_bytecode=True
os.environ['ELS_RUNTIME_IMAGE']=str(R/'analysis/client-6c6b5180/x2-runtime.bin')
bindings=json.loads((HERE.parent/'source-bindings.json').read_bytes())
import hashlib
for row in bindings['source_files']:
    assert hashlib.sha256((RUNTIME/row['path']).read_bytes()).hexdigest()==row['sha256'],row['path']
sys.path[:0]=[str(RUNTIME),str(RUNTIME/'tools'),str(R/'tools'),str(R/'tools/pylibs')]
from els_server.domain import dungeon_result_rules as rules,dungeon_result_stats as result
from els_server.storage.reward_state import RewardState,RewardConflict
from els_server.domain.dungeon_clear import reward_clear_notice
import original_statistics_checks as base
path=HERE/'fixtures/previous_reward_state.py'
assert hashlib.sha256(path.read_bytes()).hexdigest()==bindings['previous_reward_reader_sha256']
spec=importlib.util.spec_from_file_location('previous_reward_reader',path)
previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)

def decoded(r,raw):
    data=r.alloc(len(raw));r.write(data,raw);buf=r.alloc(48)
    r.write(buf+8,struct.pack('<QQQ',data,data+len(raw),data+len(raw)))
    stream=r.alloc(40);dto=r.alloc(0x140)
    r.call(0xc7a810,dto);r.call(0x3b6d140,stream);r.call(0x3b6d1c0,stream,buf,0)
    assert r.call(0xda64c0,stream,dto)&255==1
    assert struct.unpack('<I',r.read(buf+32,4))[0]==len(raw)
    begin,end=struct.unpack('<QQ',r.read(dto+0x1b,16))
    assert (end-begin)%0x1c9==0
    return [dict(uid=struct.unpack('<Q',r.read(p,8))[0],rank=r.read(p+0x17c,1)[0],
        mvp=r.read(p+0x17d,1)[0],awards=list(r.read(p+0x17e,3)),
        contribution=struct.unpack('<f',r.read(p+0x174,4))[0])for p in range(begin,end,0x1c9)]

def identity_effect(db,uid,source,ed,xp,dungeon):
    return dict(ed=ed,experience=xp,base_ed=ed,base_experience=xp,bonus_ed=0,bonus_experience=0)

class RulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.native=base.Replay()

    def member(self,uid,*,own=100,total=None,support=0,reduction=0,hp=0,mp=0,own_hp=0,own_mp=0,cd=None,power=100):
        s=base.session(uid);s.dungeon_id=30000;s.dungeon_result_power=(uid,power)
        total=own if total is None else total
        raw=base.native_report(self.native,uid,(total,0,total,own,0,own,support,reduction),(hp,mp,own_hp,own_mp),10)
        raw=base.recipient_report(raw,cd or {})
        parsed=base.hp_report(raw,statistics=True)
        s.dungeon_result_report=(result.generation(s),1,parsed)
        return s

    def test_equal_contributions_rank_ss_and_one_stable_mvp(self):
        members=[self.member(uid)for uid in(1001,1002)]
        plans=rules.assess(members,'run-a')
        self.assertEqual([p.score_bp for p in plans.values()],[5000,5000])
        self.assertEqual([p.rank for p in plans.values()],[8,8])
        self.assertEqual(sum(p.mvp for p in plans.values()),1)
        self.assertEqual(sum(p.awards[0]for p in plans.values()),1)
        self.assertEqual(plans,rules.assess(list(reversed(members)),'run-a'))

    def test_attack_support_counts_and_received_damage_does_not_penalize(self):
        members=[self.member(1001,own=100,total=1000),self.member(1002,own=0,support=900)]
        plans=rules.assess(members,'run-a')
        self.assertGreater(plans[1002].score_bp,plans[1001].score_bp)
        self.assertTrue(plans[1002].mvp)
        # Reporter9999's copies in every native map are deliberately ignored.
        self.assertEqual(plans[1001].inputs[0],100)

    def test_cooldown_and_party_recovery_have_separate_units(self):
        members=[self.member(1001,own=1000,hp=5000,own_hp=5000,cd={1002:12}),
                 self.member(1002,own=0,hp=300,mp=200)]
        plans=rules.assess(members,'run-cd')
        self.assertEqual(plans[1001].inputs[2:],(0,0,0))
        self.assertEqual(plans[1002].inputs[2:],(300,200,12))
        self.assertEqual(plans[1001].score_bp,7777)
        self.assertEqual(plans[1002].score_bp,2222)

    def test_power_normalization_does_not_select_mvp(self):
        members=[self.member(1001,own=600,power=900),self.member(1002,own=400,power=100)]
        plans=rules.assess(members,'run-power')
        self.assertTrue(plans[1001].mvp)
        self.assertEqual(plans[1001].completion,66)
        self.assertEqual(plans[1001].rank,5) # B; lower than the weaker member's SS.
        self.assertEqual(plans[1002].rank,8)

    def test_solo_missing_and_zero_reports_are_distinct(self):
        s=self.member(1001,own=0)
        zero=rules.assess([s],'zero')[1001]
        self.assertEqual(zero.rank,1);self.assertTrue(zero.mvp);self.assertFalse(any(zero.awards))
        del s.dungeon_result_report
        missing=rules.assess([s],'missing')[1001]
        self.assertEqual(missing.rank,0);self.assertTrue(missing.mvp)

    def test_category_minimum_and_multi_award_single_rate(self):
        s=self.member(1001,own=.25,reduction=.5,hp=.25,mp=.25)
        plan=rules.assess([s],'below')[1001];self.assertFalse(any(plan.awards))
        s=self.member(1001,own=100,reduction=10,hp=50,mp=40)
        plan=rules.assess([s],'all')[1001]
        self.assertEqual(plan.awards,(True,True,True));self.assertEqual(plan.bonus_bp,1000)

    def test_scale_and_roster_order_invariance(self):
        baseline=None
        for scale in(1,2,8,1024):
            members=[self.member(1001,own=15*scale,power=100*scale),self.member(1002,own=85*scale,power=300*scale)]
            plans=rules.assess(members,'invariance')
            values={uid:(p.score_bp,p.rank,p.mvp,p.awards)for uid,p in plans.items()}
            if baseline is None:baseline=values
            self.assertEqual(values,baseline)

    def test_equal_three_member_grade_is_not_reduced_by_display_rounding(self):
        members=[self.member(uid)for uid in(1001,1002,1003)]
        plans=rules.assess(members,'three')
        self.assertTrue(all(p.score_bp==3333 and p.completion==100 and p.rank==8 for p in plans.values()))

    def test_clear_snapshot_survives_later_reports(self):
        members=[self.member(1001),self.member(1002)]
        room=N(seed='snapshot',members=tuple(members))
        for s in members:
            s.dungeon_participants=frozenset((1001,1002));s.application=N(world=N(dungeons=N(room=lambda _:room)))
        plan=rules.prepare_clear(members[0])
        members[0].dungeon_result_report[2].statistics['damage'][3][1001]=1e30
        self.assertIs(rules.prepare_clear(members[0]),plan)

    def test_uncommitted_plan_refreshes_on_new_report_sequence(self):
        members=[self.member(1001),self.member(1002)]
        room=N(seed='retry',members=tuple(members))
        for s in members:
            s.dungeon_participants=frozenset((1001,1002));s.application=N(world=N(dungeons=N(room=lambda _:room)))
        first=rules.prepare_clear(members[0])
        changed=self.member(1001,own=10000).dungeon_result_report[2]
        members[0].dungeon_result_report=(result.generation(members[0]),2,changed)
        second=rules.prepare_clear(members[0])
        self.assertIsNot(first,second);self.assertGreater(second.score_bp,first.score_bp)

    def test_native_c1_contribution_rank_and_awards(self):
        s=self.member(1001,own=100,reduction=10,hp=50,mp=40)
        plan=rules.assess([s],'native')[1001]
        raw=rules.result_payload(reward_clear_notice(132,55,1001,map_id=30000).payload,plan)
        row=decoded(self.native,raw)[0]
        self.assertEqual(row,dict(uid=1001,rank=8,mvp=1,awards=[1,1,1],contribution=100))


class EconomyTests(RulesTests):
    # Inherit the native fixture helper without repeating the numerical suite.
    def setUp(self):
        root=ARTIFACTS/'test-private';root.mkdir(exist_ok=True)
        self.temporary=tempfile.TemporaryDirectory(dir=root);self.path=Path(self.temporary.name)/'game.sqlite3'
        self.store=RewardState(self.path)
        self.modifier=patch('els_server.domain.title_economy.resolve',side_effect=identity_effect);self.modifier.start()
    def tearDown(self):self.modifier.stop();self.temporary.cleanup()
    def assessment(self,uid=1001,run=None):
        s=self.member(uid,own=100,reduction=10,hp=50,mp=40)
        if run is not None:s.reward_run_id=run
        return rules.assess([s],s.reward_run_id)[uid]
    def grant(self,plan,store=None,**options):
        return(store or self.store).grant(plan.run_id,b'authoritative-clear-proof',120,50,
            lambda balances,best,economy:reward_clear_notice(economy['ed'],economy['experience'],plan.uid,map_id=30000).payload,
            dungeon_clear=(30000,83),title_economy='clear',dungeon_result=plan,**options)

    def test_bonus_cold_read_retry_and_old_reader(self):
        plan=self.assessment();first=self.grant(plan)
        self.assertEqual(first['balances'],dict(ed=132,experience=55,revision=1))
        self.assertEqual(decoded(self.native,first['response'])[0]['rank'],8)
        cold=RewardState(self.path);second=self.grant(replace(plan,score_bp=0,mvp=False,awards=(False,)*3,bonus_bp=0),cold)
        self.assertTrue(second['replayed']);self.assertEqual(second['response'],first['response'])
        old=previous.RewardState(self.path).grant(plan.run_id,b'authoritative-clear-proof',120,50,
            lambda *_:self.fail('Historical reader must replay'),dungeon_clear=(30000,83),title_economy='clear')
        self.assertEqual(old['response'],first['response']);self.assertEqual(cold.balances(),first['balances'])
        with closing(sqlite3.connect(self.path))as db:
            grant=json.loads(db.execute('SELECT grant_json FROM reward_receipts').fetchone()[0])
            self.assertNotIn('dungeon_result',grant)
            effect=json.loads(db.execute('SELECT effect_json FROM reward_title_receipts').fetchone()[0])
            self.assertEqual(effect['dungeon_result']['version'],rules.policy()[0]['version'])
            self.assertEqual(effect['dungeon_result']['applied_ed'],12)

    def test_legacy_receipt_never_receives_topup(self):
        plan=self.assessment()
        old=previous.RewardState(self.path).grant(plan.run_id,b'authoritative-clear-proof',120,50,
            lambda balances,best,economy:reward_clear_notice(economy['ed'],economy['experience'],1001,map_id=30000).payload,
            dungeon_clear=(30000,83),title_economy='clear')
        new=self.grant(plan)
        self.assertTrue(new['replayed']);self.assertEqual(new['response'],old['response'])
        self.assertEqual(self.store.balances(),dict(ed=120,experience=50,revision=1))

    def test_owner_source_and_failed_payload_reject_without_increment(self):
        plan=self.assessment()
        with self.assertRaises(ValueError):self.grant(replace(plan,uid=1002))
        from els_server.domain.dungeon_clear import failed_clear_notice
        with self.assertRaises(ValueError):
            self.store.grant(plan.run_id,b'authoritative-clear-proof',120,50,
                lambda *_:failed_clear_notice(1001,map_id=30000).payload,
                dungeon_clear=(30000,83),title_economy='clear',dungeon_result=plan)
        self.assertEqual(self.store.balances(),dict(ed=0,experience=0,revision=0))

    def test_group_sql_failure_rolls_back_all_members_and_bonuses(self):
        a=self.assessment();b=self.assessment(1002);second=RewardState(self.path,1002)
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute("CREATE TRIGGER reject_second BEFORE INSERT ON reward_receipts WHEN NEW.run_id='"+b.run_id+"' BEGIN SELECT RAISE(ABORT,'second member failure');END")
        with self.assertRaises(sqlite3.IntegrityError),closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE');self.grant(a,transaction=db);self.grant(b,second,transaction=db)
        self.assertEqual(self.store.balances(),dict(ed=0,experience=0,revision=0))
        self.assertEqual(second.balances(),dict(ed=0,experience=0,revision=0))
        with closing(sqlite3.connect(self.path))as db:self.assertEqual(db.execute('SELECT COUNT(*)FROM reward_title_receipts').fetchone()[0],0)

    def test_experience_limit_and_large_report_never_increase_bonus_rate(self):
        s=self.member(1001,own=1e30);plan=rules.assess([s],s.reward_run_id)[1001]
        receipt=self.grant(plan,experience_limit=51)
        self.assertEqual(receipt['balances'],dict(ed=132,experience=51,revision=1))
        effect=receipt['title_economy']['dungeon_result']
        self.assertEqual(effect['ordinary_experience'],1)

if __name__=='__main__':
    suite=unittest.TestSuite()
    for cls in(base.Checks,RulesTests):suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(cls))
    # Only EconomyTests' own cases: do not rerun inherited rule-only methods.
    suite.addTests(EconomyTests(name)for name in EconomyTests.__dict__ if name.startswith('test_'))
    checked=unittest.TextTestRunner(verbosity=2).run(suite)
    evidence=json.dumps(dict(passed=checked.wasSuccessful(),tests=checked.testsRun,
        failures=len(checked.failures),errors=len(checked.errors),native_writer='DA2F50',native_reader='DA64C0',
        legacy_reader_replay=True,old_receipt_topup=False),indent=2)+'\n'
    (ARTIFACTS/('core-verification-'+uuid.uuid4().hex[:8]+'.json')).write_text(evidence)
    (ARTIFACTS/'core-verification.json').write_text(evidence)
    raise SystemExit(not checked.wasSuccessful())
