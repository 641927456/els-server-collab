"""Native group identities and retained source/account boundaries."""
from qa_environment import F
from contextlib import closing
import hashlib,json,sqlite3,time,unittest
from els_server.storage import achievement_history as history
from els_server.domain.consumables import catalog
from els_server.game_data import client_data


class ConsumptionSources(unittest.TestCase):
    def test_native_cooltime_groups_are_not_shortcut_binding_IDs(self):
        groups={2,4,5,6,15,40};enum=client_data().resource('Enum.lua')['COOLTIME_ITEM_GROUP']
        self.assertEqual({enum[k]for k in('CIG_FOOD','CIG_MP_POTION','CIG_DRINK','CIG_THROW_ITEM','CIG_FULL_RECOVER_ITEM','CIG_GUILD_POTION')},groups)
        templates={group:next(t for t,row in catalog().items()if row['cooldown_group']==group)for group in groups}
        with closing(sqlite3.connect(':memory:'))as db,db:
            db.execute('CREATE TABLE character_owners(uid INTEGER PRIMARY KEY,account_id INTEGER NOT NULL)')
            db.executemany('INSERT INTO character_owners VALUES(?,?)',[(1001,1),(1002,1),(1003,2)])
            db.execute('CREATE TABLE consumable_uses(operation_id TEXT PRIMARY KEY,owner INTEGER,template INTEGER)')
            db.execute('CREATE TABLE known_resurrection_spends(operation_id TEXT PRIMARY KEY,owner INTEGER,run TEXT,life INTEGER,UNIQUE(owner,run,life))')
            expected={}
            for n,group in enumerate(sorted(groups),1):
                expected[(35,group)]=n
                db.executemany('INSERT INTO consumable_uses VALUES(?,?,?)',
                    [(str(group)+':'+str(i),1001+i%2,templates[group])for i in range(n)])
                db.execute('INSERT INTO consumable_uses VALUES(?,?,?)',('foreign'+str(group),1003,templates[group]))
            db.executemany('INSERT INTO known_resurrection_spends VALUES(?,?,?,?)',
                [('paid-a',1001,'one-run',1),('paid-alt',1002,'other-run',1),('paid-foreign',1003,'third-run',1)])
            expected[(36,0)]=2
            before=list(db.iterdump())
            self.assertEqual(history.counts(db,1,{35,36}),expected)
            self.assertEqual(history.counts(db,2,{36}),{(36,0):1})
            self.assertEqual(list(db.iterdump()),before)
            history.ensure_indexes(db)
            self.assertTrue(db.execute("SELECT 1 FROM sqlite_master WHERE name='native_achievement_consumable_owner_template'").fetchone())
            self.assertEqual(history.counts(db,1,{35,36}),expected)

    def test_missing_source_tables_are_read_only(self):
        with closing(sqlite3.connect(':memory:'))as db:
            self.assertEqual(history.counts(db,1,{35,36}),{})
            self.assertEqual(list(db.execute('SELECT name FROM sqlite_master')),[])


if __name__=='__main__':
    result=unittest.main(exit=False).result
    report=dict(ok=result.wasSuccessful(),tests=result.testsRun,production_database_access=False,
        native_cooltime_groups=[2,4,5,6,15,40],fixture='Retained receipt/account boundary and exact current enum groups',
        errors=[v[-2000:]for _,v in result.errors],failures=[v[-2000:]for _,v in result.failures],
        source_sha256=hashlib.sha256((F/'source-v1/els_server/storage/achievement_history.py').read_bytes()).hexdigest())
    (F/('consumption-sources-'+str(time.time_ns())+'.json')).write_text(json.dumps(report,indent=2),'utf8')
    print(json.dumps(report));raise SystemExit(not report['ok'])
