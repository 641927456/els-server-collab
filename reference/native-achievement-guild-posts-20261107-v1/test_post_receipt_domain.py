"""Generated board-post receipt/account boundaries, not live guild actions."""
from pathlib import Path
from contextlib import closing
import hashlib,json,os,sqlite3,sys,time,unittest
F=Path(__file__).resolve().parent;R=Path('G:/els');B=R/'releases/online/native-achievement-foundation-20261107-v1'
sys.dont_write_bytecode=True
sys.path[:0]=[str(B),str(B/'vendor'),str(R/'tools/pylibs'),str(R/'analysis/pr771-racing-local-20261103-v1/test-libs')]
os.environ['HYPOTHESIS_STORAGE_DIRECTORY']=str(F/'hypothesis-storage')
import els_server.storage
els_server.storage.__path__.insert(0,str(F/'source-v1/els_server/storage'))
from els_server.storage import achievement_history as history,guild_system_state as system
from els_server.protocol.guild_system_messages import reply
from hypothesis import given,settings,example,strategies as st


class PostReceiptDomain(unittest.TestCase):
    @settings(max_examples=30,deadline=None,database=None)
    @example(1001)
    @example(2**63-3)
    @given(st.integers(min_value=1001,max_value=2**63-3))
    def test_posts_exclude_other_guild_text_actions_and_failed_ACKs(self,owner):
        with closing(sqlite3.connect(':memory:'))as db,db:
            db.execute('CREATE TABLE native_guilds(id INTEGER PRIMARY KEY)');db.execute('INSERT INTO native_guilds VALUES(1)')
            db.execute('CREATE TABLE character_owners(uid INTEGER PRIMARY KEY,account_id INTEGER NOT NULL)')
            db.executemany('INSERT INTO character_owners VALUES(?,?)',[(owner,1),(owner+1,1),(owner+2,2)])
            def record(key,actor,kind,ack,code=0):
                event=reply(ack,code.to_bytes(4,'big')+bytes((9,)))
                system.record(db,key,key,1,actor,kind,dict(events=[(event.kind,event.payload.hex())]),1794010000)
            record('self',owner,0x27d,0x27e);record('alt',owner+1,0x27d,0x27e);record('foreign',owner+2,0x27d,0x27e)
            record('failed',owner,0x27d,0x27e,1);record('wrong-ack',owner,0x27d,0x28f)
            record('announcement',owner,0x28e,0x28f);record('delete',owner,0x6a9,0x6aa)
            before=list(db.iterdump())
            self.assertEqual(history.counts(db,1,{26}),{(26,0):2})
            self.assertEqual(history.counts(db,2,{26}),{(26,0):1})
            self.assertEqual(list(db.iterdump()),before)
            history.ensure_indexes(db)
            self.assertEqual(history.counts(db,1,{26}),{(26,0):2})


if __name__=='__main__':
    result=unittest.main(exit=False).result
    report=dict(ok=result.wasSuccessful(),tests=result.testsRun,generated_examples=30,explicit_UID_boundaries=2,
        fixture='Generated retained board receipts; not actual actions',production_database_access=False,
        errors=[v[-2500:]for _,v in result.errors],failures=[v[-2500:]for _,v in result.failures],
        source_sha256=hashlib.sha256((F/'source-v1/els_server/storage/achievement_history.py').read_bytes()).hexdigest())
    (F/('post-receipt-domain-'+str(time.time_ns())+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(report));raise SystemExit(not report['ok'])
