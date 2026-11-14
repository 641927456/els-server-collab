"""Generated account isolation/replay/rollback checks; no gameplay result claims."""
from pathlib import Path
from contextlib import closing
import hashlib,json,sqlite3,sys,tempfile,time,unittest
R=Path('G:/els');W=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
BASE=R/'releases/online/native-feature-closures-20261107-v1'
sys.path[:0]=[str(BASE),str(BASE/'vendor'),str(R/'tools/pylibs'),str(R/'tools'),str(R),str(R/'analysis/pr771-racing-local-20261103-v1/test-libs')]
import els_server.domain,els_server.storage
els_server.domain.__path__.insert(0,str(W/'source-v1/els_server/domain'))
els_server.storage.__path__.insert(0,str(W/'source-v1/els_server/storage'))
from els_server.storage.game_schema import prepare
from els_server.storage.characters import Characters
from els_server.storage import achievements as state
from els_server.domain.achievement_catalog import achievement
from hypothesis import given,settings,strategies as st


class AccountState(unittest.TestCase):
    @settings(max_examples=30,deadline=None,database=None)
    @given(st.lists(st.integers(0,400),min_size=1,max_size=12))
    def test_shared_account_unique_completion_replay_rollback_and_private_displays(self,increments):
        with tempfile.TemporaryDirectory(prefix='owned-achievement-state-',dir=W)as folder:
            path=Path(folder)/'own.sqlite3';prepare(path)
            a=Characters(path,1).create('AchieveA',1,'own-create-A')['uid']
            b=Characters(path,1).create('AchieveB',2,'own-create-B')['uid']
            foreign=Characters(path,2).create('AchieveC',3,'own-create-C')['uid']
            def dump():
                with closing(sqlite3.connect(path))as db:return list(db.iterdump())
            def snapshot(account,owner):
                with closing(sqlite3.connect(path))as db:db.execute('BEGIN');return state.snapshot(db,account,owner)
            total=0;expected=set();first_dates={}
            for index,increment in enumerate(increments):
                total+=increment;updates=[]
                for ident in(13,14,15):
                    condition=achievement(ident)['conditions'][0]
                    assert condition['type']==4 and condition['parameters']['m_ePvpChannelClass']==12
                    complete=total>=condition['parameters']['m_iCount']
                    updates.append(dict(achievement=ident,condition=condition['id'],value=total,complete=complete))
                    if complete:expected.add(ident)
                owner=(a,b)[index%2];operation='own-source-'+str(index)
                with closing(sqlite3.connect(path))as db,db:
                    db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
                    result=state.record(db,1,owner,updates,operation,1794000000+index)
                before=dump()
                with closing(sqlite3.connect(path))as db,db:
                    db.execute('BEGIN IMMEDIATE')
                    self.assertEqual(state.record(db,1,owner,updates,operation,1795000000+index),dict(result,replayed=True))
                self.assertEqual(dump(),before)
                self.assertEqual(snapshot(1,a)['completed'],snapshot(1,b)['completed'])
                current=snapshot(1,a)['completed'];self.assertEqual({r['id']for r in current},expected)
                for row in current:
                    first_dates.setdefault(row['id'],row['completed_at'])
                    self.assertEqual(row['completed_at'],first_dates[row['id']]);self.assertFalse(row['received'])
                self.assertEqual(snapshot(2,foreign),dict(progress=[],completed=[],watched=[]))
            before=dump()
            with self.assertRaisesRegex(RuntimeError,'late encoding'):
                with closing(sqlite3.connect(path))as db,db:
                    db.execute('BEGIN IMMEDIATE')
                    state.record(db,1,a,[dict(achievement=16,condition=16,value=100,complete=True)],'own-failed-source',1794001000)
                    raise RuntimeError('late encoding')
            self.assertEqual(dump(),before)
            with self.assertRaisesRegex(ValueError,'source identity'):
                with closing(sqlite3.connect(path))as db,db:
                    db.execute('BEGIN IMMEDIATE')
                    state.record(db,1,a,[dict(achievement=16,condition=16,value=100,complete=True)],None,1794001000)
            self.assertEqual(dump(),before)
            with self.assertRaises(ValueError):
                with closing(sqlite3.connect(path))as db,db:
                    db.execute('BEGIN IMMEDIATE');state.record(db,2,a,[],'foreign-owner',1794001000)
            self.assertEqual(dump(),before)
            with self.assertRaisesRegex(ValueError,'Only completed'):
                with closing(sqlite3.connect(path))as db,db:
                    db.execute('BEGIN IMMEDIATE');state.toggle_display(db,1,a,425,'watch-incomplete')
            self.assertEqual(dump(),before)
            # These records are separate display-layout fixtures, not match credit.
            with closing(sqlite3.connect(path))as db,db:
                db.execute('BEGIN IMMEDIATE')
                for identity in(13,14,15,16):
                    condition=achievement(identity)['conditions'][0]
                    state.record(db,1,a,[dict(achievement=identity,condition=condition['id'],
                        value=condition['parameters']['m_iCount'],complete=True)],'display-layout-'+str(identity),1794002000)
            with closing(sqlite3.connect(path))as db,db:
                db.execute('BEGIN IMMEDIATE')
                for identity in(13,14,15):state.toggle_display(db,1,a,identity,'watch-'+str(identity))
            self.assertEqual(snapshot(1,a)['watched'],[13,14,15]);self.assertEqual(snapshot(1,b)['watched'],[])
            before=dump()
            with self.assertRaisesRegex(ValueError,'full'):
                with closing(sqlite3.connect(path))as db,db:
                    db.execute('BEGIN IMMEDIATE');state.toggle_display(db,1,a,16,'watch-full')
            self.assertEqual(dump(),before)
            with closing(sqlite3.connect(path))as db,db:
                db.execute('BEGIN IMMEDIATE');state.toggle_display(db,1,a,14,'watch-remove')
            before=dump()
            with closing(sqlite3.connect(path))as db,db:
                db.execute('BEGIN IMMEDIATE');self.assertEqual(state.toggle_display(db,1,a,14,'watch-remove'),[13,15])
            self.assertEqual(dump(),before)


if __name__=='__main__':
    result=unittest.main(exit=False).result
    report=dict(ok=result.wasSuccessful(),properties=result.testsRun,generated_examples=30,
        storage_mechanics_only=True,actual_PvP_matches=False,production_database_access=False,
        source_sha256={name:hashlib.sha256((W/'source-v1/els_server'/name).read_bytes()).hexdigest()for name in('storage/achievements.py','domain/achievement_catalog.py')},
        errors=[detail[-1800:]for _,detail in result.errors],failures=[detail[-1800:]for _,detail in result.failures])
    (W/('account-state-properties-'+str(time.time_ns())+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    raise SystemExit(not report['ok'])
