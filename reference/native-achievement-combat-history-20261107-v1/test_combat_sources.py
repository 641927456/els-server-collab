"""Boundary times, account attribution and approved cumulative PvP authority."""
from qa_environment import F
from contextlib import closing
from dataclasses import asdict
import hashlib,json,sqlite3,tempfile,time,unittest
from fixture_helpers import balanced_profiles,register_fixture
from els_server.storage.characters import Characters
from els_server.storage.game_schema import prepare as prepare_store
from els_server.storage import achievement_history as history,achievement_profiles as profiles,achievements as state
from els_server.domain.pvp_official_1v1_policy import Profile,plan,POLICY,CHANNEL_CLASS


class CombatSources(unittest.TestCase):
    def test_timed_boundaries_and_account_best_are_real_conditions(self):
        with tempfile.TemporaryDirectory(prefix='owned-timed-source-',dir=F)as folder:
            path=F/folder/'game.sqlite3'
            prepare_store(path)
            a=Characters(path,1).create('TimeSource',1,'owned-timed-a')['uid']
            alt=Characters(path,1).create('TimeAlt',2,'owned-timed-alt')['uid']
            foreign=Characters(path,2).create('TimeOther',3,'owned-timed-other')['uid']
            with closing(sqlite3.connect(path))as db,db:
                db.execute('INSERT INTO dungeon_records VALUES(?,?,?)',(a,41400,601))
                db.execute('INSERT INTO dungeon_records VALUES(?,?,?)',(foreign,41400,1))
                db.execute('INSERT INTO dungeon_records VALUES(?,?,?)',(alt,30000,1))
                profiles.reconcile(db,1,a,1000,condition_types={2})
                self.assertEqual(state.snapshot(db,1,a)['completed'],[])
                before=list(db.iterdump());self.assertEqual(history.counts(db,1,{2}),{(2,41400):601,(2,30000):1})
                self.assertEqual(list(db.iterdump()),before)
                db.execute('INSERT INTO dungeon_records VALUES(?,?,?)',(alt,41400,600))
                for seconds,expected in((600,[2]),(481,[2]),(480,[2,3]),(301,[2,3]),
                        (300,[2,3,4]),(91,[2,3,4]),(90,[2,3,4,5]),(61,[2,3,4,5]),(60,[2,3,4,5,6])):
                    db.execute('UPDATE dungeon_records SET seconds=?WHERE uid=?AND map_id=41400',(seconds,alt))
                    profiles.reconcile(db,1,a,1000+seconds,condition_types={2})
                    self.assertEqual(sorted(r['id']for r in state.snapshot(db,1,a)['completed']),expected)
                before=state.snapshot(db,1,a)
                profiles.reconcile(db,1,alt,2000,condition_types={2})
                self.assertEqual(state.snapshot(db,1,a),before)
                self.assertEqual(state.snapshot(db,1,alt)['completed'],before['completed'])

    def test_policy_counters_sum_owned_roles_and_exclude_unknown_histories(self):
        with tempfile.TemporaryDirectory(prefix='owned-pvp-source-',dir=F)as folder:
            path=F/folder/'game.sqlite3';actors=[]
            prepare_store(path)
            for account,name,unit in((1,'PvpSource',1),(1,'PvpAlt',2),(2,'PvpOther',3),(1,'PvpLegacy',4)):
                actors.append(dict(account_id=account,uid=Characters(path,account).create(name,unit,'owned-'+name)['uid']))
            with closing(sqlite3.connect(path))as db,db:db.execute('UPDATE characters SET level=75')
            pair=balanced_profiles()
            register_fixture(path,actors[0],pair[0]);register_fixture(path,actors[1],Profile(completed=3,wins=2,losses=1))
            register_fixture(path,actors[2],pair[1])
            with closing(sqlite3.connect(path))as db,db:
                db.execute('INSERT INTO official_pvp_profiles VALUES(?,?,?,?,0,?)',
                    (actors[3]['uid'],1,'unknown-legacy','not-a-current-profile','owned-unadopted-legacy'))
                expected={(4,12):101,(5,12):100};before=list(db.iterdump())
                self.assertEqual(CHANNEL_CLASS,12)
                self.assertEqual(history.counts(db,1,{4,5}),expected)
                self.assertEqual(history.counts(db,2,{4,5}),{(4,12):99,(5,12):99})
                self.assertEqual(history.counts(db,3,{4,5}),{(4,12):0,(5,12):0})
                self.assertEqual(list(db.iterdump()),before)
                history.ensure_indexes(db)
                self.assertTrue(db.execute("SELECT 1 FROM sqlite_master WHERE name='native_achievement_pvp_profile_account'").fetchone())
                self.assertEqual(history.counts(db,1,{4,5}),expected)
                # Use the actual approved draw and leave plans; their AP/RP
                # changes must not masquerade as new wins or defeats.
                current=pair[0]
                for outcome in('draw','leave'):
                    current=plan(current,pair[1],outcome=outcome,level=75).after
                    db.execute('UPDATE official_pvp_profiles SET profile_json=?WHERE uid=?',
                        (json.dumps(asdict(current)),actors[0]['uid']))
                    self.assertEqual(history.counts(db,1,{4,5}),expected)

    def test_missing_tables_are_read_only(self):
        with closing(sqlite3.connect(':memory:'))as db:
            self.assertEqual(history.counts(db,1,{2,4,5}),{})
            self.assertEqual(list(db.execute('SELECT name FROM sqlite_master')),[])


if __name__=='__main__':
    r=unittest.main(exit=False).result
    proof=dict(ok=r.wasSuccessful(),tests=r.testsRun,errors=[v[-2400:]for _,v in r.errors],
        failures=[v[-2400:]for _,v in r.failures],production_database_access=False,
        source_sha256={p.relative_to(F/'source-v1').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in(F/'source-v1').rglob('*.py')})
    (F/('combat-sources-'+str(time.time_ns())+'.json')).write_bytes((json.dumps(proof,indent=2)+'\n').encode())
    print(json.dumps(proof));raise SystemExit(not proof['ok'])
