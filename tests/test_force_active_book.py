import sqlite3, struct, tempfile, unittest
from contextlib import closing
from pathlib import Path
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.domain.boosting_2026_force_inventory import catalog, owned, vector
from els_server.storage.boosting_2026_force_inventory import use_book, snapshot

class ActiveForceBookTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'state.sqlite3'
        self.account=LocalAccount(LocalState(self.path))
        self.account.enable_characters()
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE characters SET unit_class=150,level=99')
            db.execute("INSERT INTO inventory_items VALUES (990001,1001,295724,0,1,4,0)")

    def payload(self):
        return struct.pack('>QQiiIB',990001,0,0,0,0,0)

    def test_local_mapping(self):
        rule=catalog()[295724]
        self.assertEqual((rule['skill'],rule['native_rank']), (900200,1))
        self.assertEqual(owned({'force_inventory':[{'skill':900200,'rank':1,'template':295724}]})[0]['skill'],900200)

    def test_use_book_learns_active_skill(self):
        result=use_book(self.path,1001,1,self.payload(),'active-book-test')
        self.assertIsNotNone(result)
        rows=snapshot(self.path,1001)
        self.assertIn((900200,1,295724),{(r['skill'],r['rank'],r['template']) for r in rows})
        self.assertIn(struct.pack('>iBiB',900200,1,0,0),vector({'force_inventory':list(rows)}))

    def test_catalog_covers_mod_books(self):
        for template,skill in ((300550,901012),(300551,901013),(301501,901019),(390188,901032),
                               (390189,901033),(390191,901035),(390193,901037),(390195,901039)):
            rule=catalog()[template]
            self.assertEqual((rule['skill'],rule['native_rank']),(skill,1))

    def test_use_mod_book(self):
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE inventory_items SET template=390189 WHERE uid=990001')
        self.assertIsNotNone(use_book(self.path,1001,1,self.payload(),'mod-book-test'))
        rows=snapshot(self.path,1001)
        self.assertIn((901033,1,390189),{(r['skill'],r['rank'],r['template']) for r in rows})

    def test_equip_active_skill(self):
        use_book(self.path,1001,1,self.payload(),'active-book-equip')
        from els_server.storage.boosting_2026_force_equipment import active_action, snapshot_active
        equip=struct.pack('>iiiB',2,0,900200,1)
        event=active_action(self.path,1001,1,equip,'active-equip-test')
        self.assertIsInstance(event,object)
        self.assertEqual(snapshot_active(self.path,1001)[0],(900200,1))

if __name__=='__main__':
    unittest.main()
