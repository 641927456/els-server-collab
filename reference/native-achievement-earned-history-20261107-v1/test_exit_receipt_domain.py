"""Native ACK to committed-source count across the complete positive UID domain."""
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
from els_server.protocol.guild_system_messages import leave_ack,reply
from hypothesis import given,settings,example,strategies as st


class ReceiptDomain(unittest.TestCase):
    @settings(max_examples=30,deadline=None,database=None)
    @example(1001)
    @example(2**31+5)
    @example(2**63-3)
    @given(st.integers(min_value=1001,max_value=2**63-3))
    def test_harvest_is_one_plot_not_item_quantity_and_excludes_other_operations(self,owner):
        from els_server.protocol.guild_farm_messages import changed
        from els_server.domain.guild_farm import empty
        with closing(sqlite3.connect(':memory:'))as db,db:
            db.execute('CREATE TABLE native_guilds(id INTEGER PRIMARY KEY)')
            db.execute('INSERT INTO native_guilds VALUES(1)')
            db.execute('CREATE TABLE character_owners(uid INTEGER PRIMARY KEY,account_id INTEGER NOT NULL)')
            db.executemany('INSERT INTO character_owners VALUES(?,?)',[(owner,1),(owner+1,1),(owner+2,2)])
            def record(key,actor,kind,event):
                system.record(db,key,key,1,actor,kind,dict(events=[(event.kind,event.payload.hex())]),1794010000)
            record('harvest-self',owner,0x803,changed(0x804,owner,1,empty()))
            record('harvest-alt',owner+1,0x803,changed(0x804,owner+1,1,empty()))
            record('harvest-foreign',owner+2,0x803,changed(0x804,owner+2,1,empty()))
            record('failed-harvest',owner,0x803,changed(0x804,owner,1,empty(),code=1))
            record('plant',owner,0x7fd,changed(0x7fe,owner,1,empty()))
            record('remove',owner,0x7ff,changed(0x800,owner,1,empty()))
            record('wrong-event',owner,0x803,changed(0x7fe,owner,1,empty()))
            before=list(db.iterdump())
            self.assertEqual(history.counts(db,1,{56})[(56,0)],2)
            self.assertEqual(history.counts(db,2,{56})[(56,0)],1)
            self.assertEqual(list(db.iterdump()),before)

    @settings(max_examples=30,deadline=None,database=None)
    @example(1001)
    @example(2**31+5)
    @example(2**63-3)
    @given(st.integers(min_value=1001,max_value=2**63-3))
    def test_self_exit_kick_failure_other_operation_and_account_boundary(self,owner):
        with closing(sqlite3.connect(':memory:'))as db,db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('CREATE TABLE native_guilds(id INTEGER PRIMARY KEY)')
            db.execute('INSERT INTO native_guilds VALUES(1)')
            db.execute('CREATE TABLE character_owners(uid INTEGER PRIMARY KEY,account_id INTEGER NOT NULL)')
            db.executemany('INSERT INTO character_owners VALUES(?,?)',[(owner,1),(owner+1,1),(owner+2,2)])
            def record(key,actor,kind,event):
                system.record(db,key,key,1,actor,kind,dict(events=[(event.kind,event.payload.hex())]),1794010000)
            record('self',owner,0x290,leave_ack(owner,False))
            record('alt',owner+1,0x290,leave_ack(owner+1,False))
            record('foreign',owner+2,0x290,leave_ack(owner+2,False))
            record('kick',owner,0x290,leave_ack(owner+2,True))
            record('wrong-target',owner,0x290,leave_ack(owner+2,False))
            record('failed',owner,0x290,leave_ack(owner,False,1))
            record('wrong-operation',owner,0x292,leave_ack(owner,False))
            record('wrong-event',owner,0x290,reply(0x293,leave_ack(owner,False).payload))
            before=list(db.iterdump())
            self.assertEqual(history.counts(db,1,{23})[(23,0)],2)
            self.assertEqual(history.counts(db,2,{23})[(23,0)],1)
            self.assertEqual(list(db.iterdump()),before)
            history.ensure_indexes(db)
            self.assertIsNotNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='native_achievement_guild_operation_owner_kind'").fetchone())
            self.assertEqual(history.counts(db,1,{23})[(23,0)],2)
            self.assertEqual(history.counts(db,1,{24}),{})


if __name__=='__main__':
    result=unittest.main(exit=False).result
    report=dict(ok=result.wasSuccessful(),tests=result.testsRun,generated_examples=30,explicit_UID_boundaries=3,
        fixture='Generated committed-receipt shapes; not actual guild actions',production_database_access=False,
        errors=[v[-2500:]for _,v in result.errors],failures=[v[-2500:]for _,v in result.failures],
        source_sha256=hashlib.sha256((F/'source-v1/els_server/storage/achievement_history.py').read_bytes()).hexdigest())
    (F/('exit-receipt-domain-'+str(time.time_ns())+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(report));raise SystemExit(not report['ok'])
