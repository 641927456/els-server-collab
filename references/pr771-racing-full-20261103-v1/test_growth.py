"""Local-policy properties and isolated persistence; not a natural race test."""
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import collections,copy,json,random,sqlite3,struct,sys,tempfile,unittest

ROOT=Path('G:/els');W=Path(__file__).resolve().parent
R=ROOT/'analysis/pr771-firstbatch-20261103-v1/runtime'
G=ROOT/'analysis/pr771-firstbatch-20261103-v1/git'
sys.path[:0]=[str(R),str(G),str(ROOT/'analysis/pr771-racing-local-20261103-v1/test-libs')]
from hypothesis import given,settings,strategies as st
from els_server.domain import mount_racing_rules as rules
from els_server.storage import mount_growth
from els_server.storage.companion_state import handle as activate,snapshot
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items
from els_server.domain.reward_rules import item_plan
from els_server.protocol import mount_messages as wire

P=rules.policy()

@st.composite
def profiles(draw):
    exp=draw(st.integers(min_value=0,max_value=11300))
    current_level=sum(t<=exp for t in P['cumulative_experience'])
    remaining=sum(P['points_on_level'][:current_level]);stats={}
    for i in range(4):
        value=draw(st.integers(min_value=max(0,remaining-10*(3-i)),max_value=min(10,remaining)))
        if value:stats[i]=value
        remaining-=value
    assert remaining==0
    return exp,stats

class Rules(unittest.TestCase):
    @settings(max_examples=200,derandomize=True,database=None,deadline=None)
    @given(profiles(),st.integers(min_value=0,max_value=50000),st.integers(min_value=0,max_value=2**32-1))
    def test_growth_conserves_points_and_never_reduces_attributes(self,saved,amount,seed):
        exp,stats=saved;before=copy.deepcopy(stats)
        out=rules.grow(exp,stats,amount,random.Random(seed).randrange)
        self.assertEqual(out['experience'],min(11300,exp+amount))
        self.assertEqual(sum(out['stats'].values()),sum(P['points_on_level'][:out['level']]))
        self.assertTrue(all(stats.get(i,0)<=out['stats'].get(i,0)<=10 for i in range(4)))
        self.assertEqual(stats,before)
        self.assertEqual(rules.grow(out['experience'],out['stats'],0),out)

    @settings(max_examples=200,derandomize=True,database=None,deadline=None)
    @given(profiles(),st.integers(min_value=0,max_value=2**32-1))
    def test_reset_preserves_level_experience_and_total(self,saved,seed):
        exp,stats=saved
        if exp<200:
            with self.assertRaises(ValueError):rules.reset(exp,stats)
            return
        out=rules.reset(exp,stats,random.Random(seed).randrange)
        self.assertEqual((out['level'],out['experience']),(rules.level(exp),exp))
        self.assertEqual(sum(out['stats'].values()),sum(stats.values()))
        self.assertTrue(all(0<=v<=10 for v in out['stats'].values()))

    def test_curve_boundaries_and_cross_multiple_levels(self):
        for expected,threshold in enumerate(P['cumulative_experience'],1):
            self.assertEqual(rules.level(threshold),expected)
            if threshold:self.assertEqual(rules.level(threshold-1),expected-1)
        self.assertEqual((rules.level(6299),rules.level(6300)),(14,15))
        out=rules.grow(0,{},100000,lambda n:0)
        self.assertEqual(out,dict(level=20,experience=11300,stats={0:10,1:10,2:10}))
        self.assertEqual(rules.grow(out['experience'],out['stats'],1),out)

    def test_capped_attribute_is_removed_from_the_draw_pool(self):
        sizes=[]
        out=rules.allocate({0:10,1:9,2:10},2,lambda n:sizes.append(n) or 0)
        self.assertEqual(out,{0:10,1:10,2:10,3:1})
        self.assertEqual(sizes,[2,1])

    def test_all_reward_intervals_and_native_reward_types(self):
        for rank in range(1,4):
            counts=collections.Counter()
            for roll in range(100):
                out=rules.reward(rank,6,lambda n:roll);kind=out['bonus_type'];counts[kind]+=1
                if kind<6:
                    self.assertIsNone(out['item'])
                    self.assertEqual(out['experience'],P['rank_experience'][rank-1]*P['experience_multiplier_percent'][kind]//100)
                else:
                    self.assertEqual(out['experience'],P['rank_experience'][rank-1])
                    self.assertEqual(out['item'],dict(template=714109 if kind<11 else 714108,quantity=kind-5 if kind<11 else 1))
            self.assertEqual([counts[i]for i in range(12)],P['bonus_weights_by_rank'][str(rank)])
        def no_draw(n):raise AssertionError('Unexpected bonus draw')
        for lanes in range(3,7):
            for rank in range(1,lanes+1):
                if lanes==6 and rank<=3:continue
                self.assertEqual(rules.reward(rank,lanes,no_draw),dict(experience=P['rank_experience'][rank-1],bonus_type=-1,item=None))

    def test_result_distinguishes_nominal_and_effective_experience(self):
        saved=rules.profile(11300,{0:10,1:10,2:1,3:9})
        result=rules.result(saved['experience'],saved['stats'],1,6,lambda n:99)
        self.assertEqual(result['profile'],saved)
        self.assertEqual(result['experience_gained'],0)
        self.assertEqual(result['reward']['item'],dict(template=714108,quantity=1))
        self.assertEqual(result['reward']['experience'],120)

    def test_invalid_profiles_and_inputs_reject_before_randomness(self):
        def no_draw(n):raise AssertionError('Invalid input consumed randomness')
        for exp,stats in [(-1,{}),(11301,{}),(True,{}),(200,{}),(0,{4:0}),(0,{False:0}),(0,{0:True}),(0,{0:-1}),(200,{0:11})]:
            with self.assertRaises(ValueError):rules.grow(exp,stats,1,no_draw)
        for rank,lanes in [(0,6),(7,6),(1,2),(1,7),(True,6),(1,True)]:
            with self.assertRaises(ValueError):rules.reward(rank,lanes,no_draw)
        for amount in (-1,True,1.5):
            with self.assertRaises(ValueError):rules.grow(0,{},amount,no_draw)

class Persistence(unittest.TestCase):
    def setUp(self):
        clock=patch('els_server.storage.mount_state.time.time',return_value=1000);clock.start();self.addCleanup(clock.stop)
        self.tmp=tempfile.TemporaryDirectory(dir=W);self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'save.sqlite3'
        a=LocalAccount(LocalState(self.path));a.enable_characters();a.get_inventory_snapshot()
        with closing(sqlite3.connect(self.path)) as db,db:
            items=grant_items(db,[item_plan(550431,1)])
        activate(self.path,1001,0x432,struct.pack('>Q',items[0]['uid']),'mount-activate')
        self.mount=next(p for p in snapshot(self.path,1001)['companions']if p['kind']=='mount')
        self.uid=self.mount['uid']

    def test_default_read_is_nonmutating_and_native_default_bytes_match(self):
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(mount_growth.read(db,1001,self.uid),rules.profile())
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='mount_growth'").fetchone())
        raw=wire.record(self.mount)
        self.assertEqual(raw[-19:],struct.pack('>QHBiI',self.uid,self.mount['unit'],1,0,0))

    def test_cold_snapshot_summon_and_repeated_complete_save(self):
        value=rules.grow(0,{},11300,lambda n:0)
        for _ in range(2):
            with closing(sqlite3.connect(self.path)) as db,db:
                db.execute('BEGIN IMMEDIATE');self.assertEqual(mount_growth.save(db,1001,self.uid,value),value)
        cold=next(p for p in snapshot(self.path,1001,enter_world=True)['companions']if p['uid']==self.uid)
        self.assertEqual(cold['racing'],value)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM mount_growth').fetchone()[0],1)
        from els_server.storage.mount_state import handle
        answer=handle(self.path,1001,0x42c,struct.pack('>QB',self.uid,1),'summon',now=1000)
        self.assertEqual(answer.payload[4:],wire.record(dict(cold,ridden=True)))
        self.assertIn(struct.pack('>QHBiI',self.uid,self.mount['unit'],20,11300,3),answer.payload)

    def test_rollback_and_foreign_owner_rejection(self):
        value=rules.grow(0,{},200,lambda n:0)
        with closing(sqlite3.connect(self.path)) as db:
            with self.assertRaisesRegex(ValueError,'serialization failure'):
                with db:
                    db.execute('BEGIN IMMEDIATE');mount_growth.save(db,1001,self.uid,value)
                    raise ValueError('serialization failure')
            self.assertEqual(mount_growth.read(db,1001,self.uid),rules.profile())
            with self.assertRaises(ValueError):mount_growth.save(db,1001,self.uid,value)
            with self.assertRaises(ValueError):
                with db:
                    db.execute('BEGIN IMMEDIATE');mount_growth.save(db,1002,self.uid,value)
            with db:
                db.execute('BEGIN IMMEDIATE');mount_growth.save(db,1001,self.uid,value)
            with self.assertRaises(ValueError):mount_growth.read(db,1002,self.uid)
            with self.assertRaises(ValueError):
                with db:
                    db.execute('BEGIN IMMEDIATE');mount_growth.save(db,1001,self.uid,dict(value,level=20))
            self.assertEqual(mount_growth.read(db,1001,self.uid),value)

    def test_timed_mount_cannot_receive_persistent_growth(self):
        from els_server.storage.mount_state import assign_lifetime
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            assign_lifetime(db,1001,self.mount,dict(group=4,slot=0,template=550431),1,1000)
        with closing(sqlite3.connect(self.path)) as db:
            with self.assertRaises(ValueError):
                with db:
                    db.execute('BEGIN IMMEDIATE');mount_growth.save(db,1001,self.uid,rules.grow(0,{},200,lambda n:0))
            self.assertEqual(mount_growth.read(db,1001,self.uid),rules.profile())

if __name__=='__main__':unittest.main()
