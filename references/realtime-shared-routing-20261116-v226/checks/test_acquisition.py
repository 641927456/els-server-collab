"""Real authorization functions and transaction ledger, SQLite :memory: only."""
import importlib.util,json,sqlite3,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
import argparse
parser=argparse.ArgumentParser(add_help=False)
parser.add_argument('--runtime',type=Path,required=True)
options,rest=parser.parse_known_args()
sys.argv[1:]=rest
SRC=options.runtime.resolve(strict=True)
sys.path[:0]=[str(SRC),str(SRC/'vendor')]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
old=load('old_acquisition',SRC/'els_server/domain/acquisition_policy.py')
new=load('new_acquisition',ROOT/'source/els_server/domain/acquisition_policy.py')
from els_server.domain.raid_reward_items import _RaidSource,_SEAL,ensure_sources,plain_plan
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS

class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.db.execute('BEGIN');ensure_sources(self.db)
        self.checks=0;self.enabled=True
    def tearDown(self):self.db.close()
    def source(self,template=130047,identity=None,plan=None):
        plan=plan or [dict(template=template,metadata=VERIFIED_TEMPLATES[template],group=TEMPLATE_BAG_GROUPS[template],quantity=1)]
        identity=identity or {'policy':'ordinary-test-source','owner':1001}
        def guard(db):self.checks+=1;return self.enabled
        self.db.execute('INSERT OR REPLACE INTO raid_reward_sources VALUES (?,?,?,?,?)',('operation',1001,'box',plain_plan(identity),plain_plan(plan)))
        return _RaidSource(_SEAL,self.db,1001,'operation','box',identity,plan,guard)
    def result(self,module,t,source):
        try:return ('return',module.can_acquire(t,raid_reward_source=source))
        except Exception as e:return (type(e).__name__,str(e))
    def test_generic_templates_have_identical_decisions(self):
        for t in (130047,77000,77200,111087,135909,136113,136174,136175,295750,295762,711786):
            with self.subTest(template=t):
                if t not in VERIFIED_TEMPLATES:continue
                s=self.source(t);self.assertEqual(self.result(old,t,s),self.result(new,t,s))
    def test_source_qualification_failures_are_not_bypassed(self):
        from els_server.domain.periodic_reward_items import POLICY,PREMIUM_POLICY,WEEKLY_POLICY
        from els_server.domain.promotion_reward_boxes import POLICY as career
        for policy in (POLICY,PREMIUM_POLICY,WEEKLY_POLICY,career,'wedding-gifts-first-use-20261106-v1','owned-reward-boxes-20261031-v1','owned-growth-bundle-v1'):
            with self.subTest(policy=policy):
                s=self.source(identity={'policy':policy,'owner':1001})
                a=self.result(old,130047,s);b=self.result(new,130047,s)
                self.assertEqual(a,b);self.assertNotEqual(b,('return',True))
    def test_actual_owned_box_positive_plan_and_replay(self):
        from els_server.domain import owned_reward_boxes as rules
        box=next(r for r in rules.catalog()['boxes']if '0'in r['class_outputs']and not r['selection_count'])
        identity=dict(policy='owned-reward-boxes-20261031-v1',owner=1001,template=box['template'],character={},choices=[],epoch=1794787200,definition_sha256=rules.definition_sha(box['template']))
        plan=rules.plan_for(box['template'],{},(),identity['epoch']);s=self.source(identity=identity,plan=plan)
        before=self.db.total_changes
        for p in plan:
            self.assertEqual(self.result(old,p['template'],s),('return',True))
            self.assertEqual(self.result(new,p['template'],s),('return',True))
            self.assertTrue(new.can_acquire(p['template'],raid_reward_source=s))
        self.assertEqual(before,self.db.total_changes)
    def test_actual_career_box_positive_plan(self):
        from els_server.domain import promotion_reward_boxes as rules
        row=rules.catalog()['groups'][0];box=row['box'];unit=row['classes'][0]
        identity=dict(policy=rules.POLICY,owner=1001,template=box,unit_class=unit,uid=1001001,epoch=1794787200,definition_sha256=rules.definition_sha(box))
        plan=rules.plan_for(box,identity['epoch'],unit);s=self.source(identity=identity,plan=plan)
        for p in plan:
            self.assertEqual(self.result(old,p['template'],s),('return',True))
            self.assertEqual(self.result(new,p['template'],s),('return',True))
    def test_matching_native_exchange_still_checks_qualification(self):
        s=self.source(identity={'reward_source':'native-force-npc-exchange-v1','owner':1001})
        self.assertEqual(self.result(old,130047,s),self.result(new,130047,s))
        self.assertNotEqual(self.result(new,130047,s),('return',True))
    def test_revoked_authority_and_changed_ledger_rejected(self):
        s=self.source();self.enabled=False
        self.assertEqual(self.result(old,130047,s),self.result(new,130047,s))
        self.assertEqual(self.result(new,130047,s)[0],'ValueError')
        self.enabled=True;self.db.execute("UPDATE raid_reward_sources SET owner=1002")
        self.assertEqual(self.result(old,130047,s),self.result(new,130047,s))
        self.assertEqual(self.result(new,130047,s)[0],'ValueError')
    def test_outside_transaction_and_unplanned_template_rejected(self):
        s=self.source()
        self.assertEqual(self.result(old,77000,s),self.result(new,77000,s))
        self.assertEqual(self.result(new,77000,s)[0],'ValueError')
        self.db.commit()
        self.assertEqual(self.result(old,130047,s),self.result(new,130047,s))
        self.assertEqual(self.result(new,130047,s)[0],'ValueError')
    def test_positive_and_fewer_repeated_guards(self):
        s=self.source();stats={}
        # Warm identical immutable catalogs before comparing CPU work.
        self.assertEqual(self.result(old,130047,s),('return',True))
        self.assertEqual(self.result(new,130047,s),('return',True))
        for label,module in [('original',old),('candidate',new)]:
            self.checks=0;start=time.perf_counter()
            for _ in range(100):self.assertTrue(module.can_acquire(130047,raid_reward_source=s))
            stats[label]={'authority_checks_per_item':self.checks/100,'ms_per_item':(time.perf_counter()-start)*10}
        self.assertLess(stats['candidate']['authority_checks_per_item'],stats['original']['authority_checks_per_item'])
if __name__=='__main__':unittest.main(verbosity=2)
