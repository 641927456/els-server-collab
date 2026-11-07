"""Human interval rules and committed receipt projections, not natural history."""
from qa_environment import F
from contextlib import closing
import hashlib,json,sqlite3,tempfile,time,unittest
from els_server.storage.game_schema import prepare
from els_server.storage.characters import Characters
from els_server.storage import achievements as state,achievement_history as history,achievement_profiles as profiles

D=86400;BASE=1700000000


def periods():
    db=sqlite3.connect(':memory:')
    # Only columns used by the projection: these are trusted-source fixtures,
    # not a substitute for the real relationship producer/qualification test.
    db.execute('CREATE TABLE native_couple_pairs_v1(id TEXT PRIMARY KEY,a_account INTEGER,b_account INTEGER,created_at INTEGER)')
    db.execute('CREATE TABLE native_couple_closures_v1(pair_id TEXT PRIMARY KEY,created_at INTEGER)')
    db.execute('CREATE TABLE native_wedding_bookings(id INTEGER PRIMARY KEY,pair_id TEXT,finished_at INTEGER,canceled_at INTEGER)')
    db.execute('CREATE TABLE native_wedding_ceremonies(reservation INTEGER PRIMARY KEY,pair_id TEXT,at INTEGER,mode TEXT)')
    return db


class Sources(unittest.TestCase):
    def test_every_native_day_boundary_is_full24h(self):
        for target in(100,200,300,500,1000):
            with closing(periods())as db,db:
                db.execute("INSERT INTO native_couple_pairs_v1 VALUES('own',1,2,?)",(BASE,))
                for delta,expected in((-1,target-1),(0,target),(1,target)):
                    self.assertEqual(history.couple_duration(db,1,BASE+target*D+delta),(expected,BASE))
                    self.assertEqual(history.couple_duration(db,2,BASE+target*D+delta),(expected,BASE))

    def test_separate_periods_not_sum_and_remind_does_not_restart_marriage(self):
        with closing(periods())as db,db:
            db.execute("INSERT INTO native_couple_pairs_v1 VALUES('own',1,2,?)",(BASE,))
            married=BASE+90*D
            db.execute("INSERT INTO native_wedding_bookings VALUES(1,'own',?,NULL)",(married,))
            db.execute("INSERT INTO native_wedding_ceremonies VALUES(1,'own',?,'deadline')",(married,))
            self.assertEqual(history.couple_duration(db,1,BASE+180*D),(90,married))
            remind=BASE+150*D
            db.execute("INSERT INTO native_wedding_bookings VALUES(2,'own',?,NULL)",(remind,))
            db.execute("INSERT INTO native_wedding_ceremonies VALUES(2,'own',?,'ceremony')",(remind,))
            self.assertEqual(history.couple_duration(db,1,BASE+190*D),(100,married))
            db.execute("INSERT INTO native_couple_closures_v1 VALUES('own',?)",(BASE+190*D,))
            self.assertEqual(history.couple_duration(db,1,BASE+1000*D),(100,None))
            # A later role's relationship is another period; it never adds
            # its90days to this historical100days.
            db.execute("INSERT INTO native_couple_pairs_v1 VALUES('alt',1,3,?)",(BASE+910*D,))
            db.execute("INSERT INTO native_couple_pairs_v1 VALUES('foreign',4,5,?)",(BASE-2000*D,))
            before=list(db.iterdump())
            self.assertEqual(history.couple_duration(db,1,BASE+1000*D),(100,BASE+910*D))
            self.assertEqual(history.couple_duration(db,3,BASE+1000*D),(90,BASE+910*D))
            self.assertEqual(list(db.iterdump()),before)

    def test_committed_requests_and_enhancements_share_account_and_exclude_other_sources(self):
        with tempfile.TemporaryDirectory(prefix='owned-social-source-',dir=F)as folder:
            path=F/folder/'game.sqlite3';prepare(path)
            actors=[Characters(path,account).create(name,unit,'own-'+name)['uid']for account,name,unit in((1,'SocSrcA',1),(1,'SocSrcAlt',2),(2,'SocSrcOther',3))]
            with closing(sqlite3.connect(path))as db,db:
                db.execute('BEGIN IMMEDIATE');state.ensure(db)
                db.execute('CREATE TABLE inventory_action_receipts(operation_id TEXT PRIMARY KEY,request_hash TEXT,owner INTEGER,kind INTEGER,positions_json TEXT,before_json TEXT,after_json TEXT)')
                for turn in range(1,1001):
                    owner=actors[turn%2]
                    if turn<=500:state._save(db,1,owner,'duel-invite','0'*64,'request:'+str(turn),dict(target=actors[2],created_at=BASE+turn))
                    # Alternating successful/failed retained settlements:
                    # the30counter is independent of resulting item level.
                    left=[dict(uid=2000,template=60100,count=1,enhancement=7)]
                    right=[dict(left[0],enhancement=8 if turn%2 else 7)]
                    db.execute('INSERT INTO inventory_action_receipts VALUES(?,?,?,?,?,?,?)',(str(turn),'0'*64,owner,0x5ff,'[]',json.dumps(left),json.dumps(right)))
                    if turn not in(9,10,29,30,49,50,99,100,199,200,299,300,499,500,999,1000):continue
                    profiles.reconcile(db,1,actors[0],BASE+turn,condition_types={29,30})
                    expected={160+i for i,n in enumerate((10,30,50,100,500))if turn>=n}|{165+i for i,n in enumerate((100,200,300,500,1000))if turn>=n}
                    self.assertEqual({r['id']for r in state.snapshot(db,1,actors[0])['completed']},expected)
                state._save(db,2,actors[2],'duel-invite','1'*64,'foreign',{})
                state._save(db,1,actors[0],'display','2'*64,'not-request',{})
                db.execute('INSERT INTO inventory_action_receipts VALUES(?,?,?,?,?,?,?)',('amulet','3'*64,actors[0],0x219,'[]','[]','[]'))
                db.execute('INSERT INTO inventory_action_receipts VALUES(?,?,?,?,?,?,?)',('foreign','4'*64,actors[2],0x5ff,'[]','[]','[]'))
                self.assertEqual(history.counts(db,1,{29,30}),{(29,0):500,(30,0):1000})
                self.assertEqual(history.counts(db,2,{29,30}),{(29,0):1,(30,0):1})
                before=list(db.iterdump());history.counts(db,1,{29,30});self.assertEqual(list(db.iterdump()),before)
                profiles.reconcile(db,1,actors[1],BASE+1001,condition_types={29,30})
                self.assertEqual(len(state.snapshot(db,1,actors[1])['completed']),10)
                self.assertEqual(state.snapshot(db,1,actors[1])['watched'],[])

    def test_absent_sources_remain_read_only(self):
        with closing(sqlite3.connect(':memory:'))as db:
            self.assertEqual(history.counts(db,1,{29,30}),{})
            self.assertEqual(history.couple_duration(db,1,BASE),(0,None))
            self.assertEqual(list(db.execute('SELECT name FROM sqlite_master')),[])


if __name__=='__main__':
    result=unittest.main(exit=False).result
    proof=dict(ok=result.wasSuccessful(),tests=result.testsRun,errors=[v[-2600:]for _,v in result.errors],failures=[v[-2600:]for _,v in result.failures],
        production_database_access=False,fixture='Trusted committed source projections, not naturally accrued history',
        source_sha256={p.relative_to(F/'source-v1').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in(F/'source-v1').rglob('*.py')})
    (F/('sources-'+str(time.time_ns())+'.json')).write_bytes((json.dumps(proof,indent=2)+'\n').encode())
    print(json.dumps(proof));raise SystemExit(not proof['ok'])
