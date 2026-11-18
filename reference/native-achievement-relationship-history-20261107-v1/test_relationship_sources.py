"""Retained relationship generations and actual ceremony source boundaries."""
from qa_environment import F
from contextlib import closing
import hashlib,json,sqlite3,time,unittest
from els_server.storage import achievement_history as history,relationships,weddings,wedding_ceremonies


class RelationshipSources(unittest.TestCase):
    def test_two_accounts_alts_reminders_deadlines_and_read_only_queries(self):
        with closing(sqlite3.connect(':memory:'))as db,db:
            for sql in relationships.SCHEMAS.values():db.execute(sql)
            for sql in weddings.SCHEMAS.values():db.execute(sql)
            db.execute(wedding_ceremonies.SCHEMA)
            pairs=[('first',1001,1002,1,2),('alt',1003,1004,1,3),('foreign',1005,1006,4,5)]
            for name,a,b,aa,ba in pairs:
                db.execute('INSERT INTO native_couple_pairs_v1 VALUES(?,?,?,?,?,?,?,?,?,1)',
                    (name,a,b,aa,ba,10,'proposal-'+name,name,7001))
            def booking(identity,pair,at,mode):
                a,b,aa=next((a,b,aa)for name,a,b,aa,_ in pairs if name==pair)
                db.execute('''INSERT INTO native_wedding_bookings
                    (id,pair_id,owner,account_id,groom,bride,hall,officiant,ends_at,message,password,public,
                     reserved_seats,created_at,ring_json,operation,request_hash,payload,finished_at)
                    VALUES(?,?,?,?,?,?,2,0,1000,'','',1,0,10,'{}',?,'owned-fixture',X'',?)''',
                    (identity,pair,a,aa,a,b,'booking-'+str(identity),at))
                if mode is not None:
                    db.execute('INSERT INTO native_wedding_ceremonies VALUES(?,?,?,?,?)',
                        (identity,pair,at,mode,'[]'))
            booking(1,'first',100,'ceremony')
            booking(2,'first',200,'ceremony')  # Reminder keeps its own reservation.
            booking(3,'first',300,'deadline')
            booking(4,'alt',None,None)         # Merely reserved.
            booking(5,'foreign',100,'ceremony')
            before=list(db.iterdump())
            expected={1:{(18,0):2,(19,0):2},2:{(18,0):1,(19,0):2},
                3:{(18,0):1,(19,0):0},4:{(18,0):1,(19,0):1},6:{(18,0):0,(19,0):0}}
            for account,value in expected.items():self.assertEqual(history.counts(db,account,{18,19}),value)
            self.assertEqual(list(db.iterdump()),before)
            history.ensure_indexes(db)
            self.assertEqual(list(db.iterdump()),before,'These strict business tables permit no new indexes')
            self.assertTrue(relationships._present(db));self.assertTrue(weddings.present(db))

    def test_missing_tables_and_unaccepted_pair_create_no_authority(self):
        with closing(sqlite3.connect(':memory:'))as db,db:
            self.assertEqual(history.counts(db,1,{18,19}),{})
            self.assertEqual(list(db.execute('SELECT name FROM sqlite_master')),[])
            for sql in relationships.SCHEMAS.values():db.execute(sql)
            db.execute('INSERT INTO native_couple_actions_v1 VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                ('declined','owned-fixture',0x3fe,1002,1001,b'','proposal','rejected',10,'[]','[]'))
            self.assertEqual(history.counts(db,1,{18,19}),{(18,0):0})


if __name__=='__main__':
    r=unittest.main(exit=False).result
    report=dict(ok=r.wasSuccessful(),tests=r.testsRun,production_database_access=False,
        errors=[v[-2000:]for _,v in r.errors],failures=[v[-2000:]for _,v in r.failures],
        source_sha256=hashlib.sha256((F/'source-v1/els_server/storage/achievement_history.py').read_bytes()).hexdigest())
    (F/('relationship-sources-'+str(time.time_ns())+'.json')).write_bytes((json.dumps(report,indent=2)+'\n').encode())
    print(json.dumps(report));raise SystemExit(not report['ok'])
