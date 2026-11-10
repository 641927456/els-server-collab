"""Committed spa grants, exact native thresholds and immutable replay identity."""
from qa_environment import F
from pathlib import Path
from contextlib import closing
import hashlib,json,sqlite3,tempfile,time,unittest
from els_server.storage.game_schema import prepare
from els_server.storage.characters import Characters
from els_server.storage import achievements as state,achievement_history as history,achievement_profiles as profiles,environment_buffs as buffs


class Sources(unittest.TestCase):
    def test_thresholds_replays_alternative_roles_and_rollback(self):
        with tempfile.TemporaryDirectory(prefix='owned-spa-source-',dir=F)as folder:
            path=Path(folder)/'game.sqlite3';prepare(path)
            actors=[Characters(path,account).create(name,unit,'own-'+name)['uid']for account,name,unit in((1,'SpaSrcA',1),(1,'SpaSrcAlt',2),(2,'SpaSrcOther',3))]
            with closing(sqlite3.connect(path))as db,db:
                db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
                for turn in range(1,1001):
                    owner=actors[turn%2];operation='owned-spa:'+str(turn)
                    buffs.put(db,owner,'spa',operation,1700000000+turn)
                    if turn not in(99,100,299,300,499,500,699,700,999,1000):continue
                    profiles.reconcile(db,1,actors[0],1700000000+turn,condition_types={7})
                    self.assertEqual(history.counts(db,1,{7}),{(7,964):turn})
                    expected={29+i for i,n in enumerate((100,300,500,700,1000))if turn>=n}
                    self.assertEqual({r['id']for r in state.snapshot(db,1,actors[0])['completed']},expected)
                buffs.put(db,actors[0],'spa','owned-spa:1000',1700001000)
                self.assertEqual(history.counts(db,1,{7}),{(7,964):1000})
                buffs.put(db,actors[2],'spa','owned-foreign',1700001001)
                buffs.put(db,actors[0],'gate','other-source',1700001001)
                self.assertEqual(history.counts(db,2,{7}),{(7,964):1})
                self.assertEqual(history.counts(db,1,{7}),{(7,964):1000})
                profiles.reconcile(db,1,actors[1],1700002000,condition_types={7})
                self.assertEqual(len(state.snapshot(db,1,actors[1])['completed']),5)
                before=list(db.iterdump());history.counts(db,1,{7});self.assertEqual(list(db.iterdump()),before)
            with closing(sqlite3.connect(path))as db:
                db.execute('BEGIN IMMEDIATE');before=db.execute('SELECT starts_at,operation_id FROM environment_buff_sources WHERE owner=?AND source=?',(actors[0],'spa')).fetchone()
                buffs.put(db,actors[0],'spa','owned-rolled-back',1700003000);db.rollback()
                self.assertEqual(history.counts(db,1,{7}),{(7,964):1000})
                self.assertEqual(db.execute('SELECT starts_at,operation_id FROM environment_buff_sources WHERE owner=?AND source=?',(actors[0],'spa')).fetchone(),before)
                self.assertFalse(db.execute('SELECT 1 FROM native_achievement_operations WHERE operation=?',('spa-buff:owned-rolled-back',)).fetchone())

    def test_absent_source_is_read_only(self):
        with closing(sqlite3.connect(':memory:'))as db:
            before=list(db.iterdump());self.assertEqual(history.counts(db,1,{7}),{});self.assertEqual(list(db.iterdump()),before)


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Sources))
    report=dict(ok=result.wasSuccessful(),tests=result.testsRun,errors=len(result.errors),failures=len(result.failures),
        production_database_access=False,native_Game=False,natural_GUI=False,
        source_sha256={p.relative_to(F/'source-v1').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in(F/'source-v1').rglob('*.py')})
    (F/('sources-'+str(time.time_ns())+'.json')).write_bytes((json.dumps(report,indent=2)+'\n').encode())
    print(json.dumps(report));raise SystemExit(not report['ok'])
