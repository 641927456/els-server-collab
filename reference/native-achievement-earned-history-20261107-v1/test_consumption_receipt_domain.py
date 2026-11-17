"""Generated retained-receipt projections; actual operations have a TLS test."""
from pathlib import Path
from contextlib import closing
import hashlib,json,os,sqlite3,sys,time,unittest
F=Path(__file__).resolve().parent;R=Path('G:/els');B=R/'releases/online/native-achievement-foundation-20261107-v1'
sys.dont_write_bytecode=True
sys.path[:0]=[str(B),str(B/'vendor'),str(R/'tools/pylibs'),str(R/'analysis/pr771-racing-local-20261103-v1/test-libs')]
os.environ['HYPOTHESIS_STORAGE_DIRECTORY']=str(F/'hypothesis-storage')
import els_server.storage
els_server.storage.__path__.insert(0,str(F/'source-v1/els_server/storage'))
from els_server.storage import achievement_history as history
from els_server.storage.resonance_2026_resets import initialize
from els_server.domain.resonance_2026_reset_items import reset_items
from els_server.domain.resonance_category_scroll import scroll_items
from els_server.domain.owned_growth_items import install as install_owned_growth
from hypothesis import given,settings,example,strategies as st
install_owned_growth()


class ReceiptDomain(unittest.TestCase):
    @settings(max_examples=30,deadline=None,database=None)
    @example(1001,1,1)
    @example(2**63-3,1000000,2**31-1)
    @given(st.integers(min_value=1001,max_value=2**63-3),st.integers(1,1000000),st.integers(1,2**31-1))
    def test_actual_quantity_item_family_account_and_retained_weeks(self,owner,quantity,stack):
        with closing(sqlite3.connect(':memory:'))as db,db:
            db.execute('CREATE TABLE character_owners(uid INTEGER PRIMARY KEY,account_id INTEGER NOT NULL)')
            db.executemany('INSERT INTO character_owners VALUES(?,?)',[(owner,1),(owner+1,1),(owner+2,2)])
            db.execute('CREATE TABLE native_guild_quest_facts_v2(operation TEXT NOT NULL,owner INTEGER NOT NULL,week INTEGER NOT NULL,facts_json TEXT NOT NULL,PRIMARY KEY(operation,owner))')
            for key,actor,week,activities in [('old',owner,1,[(100,quantity,0),(68,1,0)]),('alt',owner+1,2,[(100,7,0)]),('foreign',owner+2,2,[(100,99,0)]),('nonhonor',owner,2,[(1,1,0)])]:
                db.execute('INSERT INTO native_guild_quest_facts_v2 VALUES(?,?,?,?)',(key,actor,week,json.dumps(dict(guild=week,activities=activities,at=1))))
            db.execute('CREATE TABLE inventory_action_receipts(operation_id TEXT PRIMARY KEY,request_hash TEXT NOT NULL,owner INTEGER NOT NULL,kind INTEGER NOT NULL,positions_json TEXT NOT NULL,before_json TEXT NOT NULL,after_json TEXT NOT NULL)')
            db.execute('CREATE INDEX inventory_action_receipts_kind_owner ON inventory_action_receipts(kind,owner)')
            def use(key,actor,kind,template,before,after):
                item=dict(uid=owner,template=template,count=before)
                db.execute('INSERT INTO inventory_action_receipts VALUES(?,?,?,?,?,?,?)',(key,key,actor,kind,'[]',json.dumps([item]),json.dumps([]if after==0 else[dict(item,count=after)])))
            use('partial',owner,0x718,189800,stack,stack-1)
            use('last',owner+1,0x718,189800,1,0)
            use('foreign',owner+2,0x718,189800,1,0)
            use('other-template',owner,0x718,712417,1,0)
            use('move',owner,0x373,189800,1,0)
            initialize(db)
            coins=sorted(reset_items().allowed['coin']);scrolls=sorted(scroll_items().allowed['scroll'])
            def reset(key,account,items):
                db.execute('INSERT INTO resonance2026_reset_receipts VALUES(?,?,?,?,?,?,?,?)',(owner,key,account,key,key,1,'[]',json.dumps([dict(uid=owner,template=t,quantity=n)for t,n in items])))
            reset('all-coins',1,[(t,quantity)for t in coins])
            reset('all-scrolls',1,[(t,1)for t in scrolls])
            reset('unknown',1,[(1,9999)])
            reset('foreign',2,[(coins[0],3),(scrolls[0],2)])
            before=list(db.iterdump())
            expected={(16,189800):2,(25,0):quantity+7,(43,0):len(coins)*quantity,(44,0):len(scrolls)}
            self.assertEqual(history.counts(db,1,{16,25,43,44}),expected)
            self.assertEqual(history.counts(db,2,{16,25,43,44}),{(16,189800):1,(25,0):99,(43,0):3,(44,0):2})
            self.assertEqual(list(db.iterdump()),before)
            history.ensure_indexes(db)
            self.assertEqual(history.counts(db,1,{16,25,43,44}),expected)
            for name in('native_achievement_guild_fact_owner','native_achievement_reset_account'):
                self.assertIsNotNone(db.execute('SELECT 1 FROM sqlite_master WHERE name=?',(name,)).fetchone())
            with self.assertRaises(sqlite3.IntegrityError):reset('all-coins',1,[(coins[0],quantity)])
            self.assertEqual(history.counts(db,1,{43})[(43,0)],len(coins)*quantity)


if __name__=='__main__':
    result=unittest.main(exit=False).result
    report=dict(ok=result.wasSuccessful(),tests=result.testsRun,generated_examples=30,explicit_boundaries=2,
        fixture='Generated immutable-receipt shapes; not actual economic actions',production_database_access=False,
        errors=[v[-2500:]for _,v in result.errors],failures=[v[-2500:]for _,v in result.failures],
        source_sha256=hashlib.sha256((F/'source-v1/els_server/storage/achievement_history.py').read_bytes()).hexdigest())
    (F/('consumption-receipt-domain-'+str(time.time_ns())+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(report));raise SystemExit(not report['ok'])
