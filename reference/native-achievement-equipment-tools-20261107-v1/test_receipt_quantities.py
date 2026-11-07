"""Generated retained receipts exercise exact quantities, levels and source families."""
import os
from qa_environment import F
os.environ['HYPOTHESIS_STORAGE_DIRECTORY']=str(F/'hypothesis-storage')
from contextlib import closing
import hashlib,json,sqlite3,time,unittest
from hypothesis import given,settings,strategies as st
from els_server.storage import achievement_history as history


def database():
    db=sqlite3.connect(':memory:')
    db.execute('CREATE TABLE character_owners(uid INTEGER PRIMARY KEY,account_id INTEGER NOT NULL)')
    db.executemany('INSERT INTO character_owners VALUES(?,?)',[(1001,1),(1002,1),(1003,2)])
    db.execute('CREATE TABLE inventory_action_receipts(operation_id TEXT PRIMARY KEY,owner INTEGER,kind INTEGER,before_json TEXT,after_json TEXT)')
    return db


def item(uid,count,template=109945,**kw):return dict(uid=uid,count=count,template=template,**kw)


def receipt(db,key,owner,kind,before,after):
    db.execute('INSERT INTO inventory_action_receipts VALUES(?,?,?,?,?)',(key,owner,kind,json.dumps(before),json.dumps(after)))


class ReceiptQuantities(unittest.TestCase):
    @settings(max_examples=60,deadline=None,database=None)
    @given(st.integers(1,999),st.integers(0,999),st.integers(1,2**63-10))
    def test_actual_units_include_removed_stacks_and_exclude_grants(self,quantity,remaining,uid):
        with closing(database())as db,db:
            for condition,kind,template in((16,0x718,189800),(45,0x1c4,109945),(60,0x6e7,361001)):
                before=[item(uid,quantity+remaining,template),item(uid+1,1,60100)]
                after=([item(uid,remaining,template)]if remaining else[])+[item(uid+1,1,60100)]
                receipt(db,str(kind),1001,kind,before,after)
                receipt(db,'other-account'+str(kind),1003,kind,before,after)
            # Preview's application and an unrelated use are zero-credit records.
            receipt(db,'apply',1001,0x6e7,[item(uid,1,60100)],[item(uid,1,60100,spell=[7])])
            receipt(db,'grant',1001,0x219,[],[item(uid,50,710012)])
            receipt(db,'refund',1001,0x1c4,[item(uid,1)],[item(uid,2)])
            before=list(db.iterdump())
            self.assertEqual(history.counts(db,1,{16,45,60}),
                {(16,189800):quantity,(45,0):quantity,(60,0):quantity})
            self.assertEqual(list(db.iterdump()),before,'Source reading must not create schema or write state')

    @settings(max_examples=60,deadline=None,database=None)
    @given(st.lists(st.tuples(st.integers(0,13),st.integers(-13,13)),min_size=0,max_size=35))
    def test_success_requires_an_increase_to_the_exact_level_without_amulets(self,levels):
        with closing(database())as db,db:
            expected={}
            for n,(old,new)in enumerate(levels):
                left=[item(2000+n,1,60100,enhancement=old)]
                right=[item(2000+n,1,60100,enhancement=new)]
                receipt(db,str(n),1001+n%2,0x5ff,left,right)
                receipt(db,'scroll'+str(n),1001,0x219,left,right)
                receipt(db,'foreign'+str(n),1003,0x5ff,left,right)
                if new in(10,11,12,13)and new>old:expected[(32,new)]=expected.get((32,new),0)+1
            self.assertEqual(history.counts(db,1,{32}),expected)

    @settings(max_examples=35,deadline=None,database=None)
    @given(st.integers(0,30),st.integers(0,30),st.integers(0,30))
    def test_special_tools_exclude_regular_crafting_and_flask_bonus_claims(self,spheres,flasks,anvils):
        with closing(database())as db,db:
            db.execute('CREATE TABLE profession_anvil_receipts(operation TEXT PRIMARY KEY,account_id INTEGER)')
            for kind,n in((0x705,spheres),(0x707,flasks),(0x9ae,3),(0x240,4)):
                for k in range(n):
                    receipt(db,str(kind)+':'+str(k),1001+k%2,kind,[],[item(5000,20)])
                    receipt(db,'foreign'+str(kind)+':'+str(k),1003,kind,[],[])
            for k in range(anvils):db.execute('INSERT INTO profession_anvil_receipts VALUES(?,1)',(str(k),))
            db.execute("INSERT INTO profession_anvil_receipts VALUES('foreign',2)")
            self.assertEqual(history.counts(db,1,{51,52,53}),{(51,0):spheres,(52,0):flasks,(53,0):anvils})
            before=list(db.iterdump());history.counts(db,2,{51,52,53});self.assertEqual(list(db.iterdump()),before)
            history.ensure_indexes(db)
            self.assertTrue(db.execute("SELECT 1 FROM sqlite_master WHERE name='native_achievement_anvil_account'").fetchone())

    def test_absent_sources_do_not_create_tables(self):
        with closing(sqlite3.connect(':memory:'))as db:
            self.assertEqual(history.counts(db,1,{16,32,34,45,51,52,53,60}),{})
            self.assertEqual(list(db.execute('SELECT name FROM sqlite_master')),[])


if __name__=='__main__':
    result=unittest.main(exit=False).result
    report=dict(ok=result.wasSuccessful(),tests=result.testsRun,generated_examples=155,
        fixture='Generated retained receipts, no actual economic actions',production_database_access=False,
        errors=[v[-2200:]for _,v in result.errors],failures=[v[-2200:]for _,v in result.failures],
        source_sha256=hashlib.sha256((F/'source-v1/els_server/storage/achievement_history.py').read_bytes()).hexdigest())
    (F/('receipt-quantities-'+str(time.time_ns())+'.json')).write_text(json.dumps(report,indent=2),'utf8')
    print(json.dumps(report));raise SystemExit(not report['ok'])
