import sqlite3, tempfile, unittest
from contextlib import closing
from pathlib import Path
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import load_items


class GmInventoryLoginTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'state.sqlite3'
        self.account = LocalAccount(LocalState(self.path)); self.account.enable_characters()

    def test_gm_granted_accessory_and_circuit_survive_cold_login(self):
        from els_server.domain.inventory_items import VERIFIED_TEMPLATES
        self.assertIn(42303, VERIFIED_TEMPLATES)
        self.assertIn(118590, VERIFIED_TEMPLATES)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('INSERT INTO inventory_items VALUES (990101,1001,42303,0,1,7,0)')
            db.execute('INSERT INTO inventory_items VALUES (990102,1001,118590,1,1,1,0)')
        with closing(sqlite3.connect(self.path)) as db:
            items = load_items(db, 1001)
        self.assertEqual({i['template'] for i in items}, {42303, 118590})


if __name__ == '__main__':
    unittest.main()
