import sqlite3, tempfile, unittest
from contextlib import closing
from pathlib import Path
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState


class GmAccessoryGrantTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'state.sqlite3'
        self.account = LocalAccount(LocalState(self.path)); self.account.enable_characters()

    def test_unverified_accessory_is_grantable(self):
        from els_server.domain.gm_item_catalog import plan
        from els_server.storage.inventory_state import grant_items
        item = plan(42303, 1)
        self.assertEqual((item['metadata'], item['group']), (0, 7))
        with closing(sqlite3.connect(self.path)) as db, db:
            grants = grant_items(db, [item], 1001)
        self.assertEqual(grants[0]['template'], 42303)
        self.assertEqual(grants[0]['group'], 7)

    def test_non_accessory_still_rejected(self):
        from els_server.domain.gm_item_catalog import plan
        with self.assertRaises(ValueError):
            plan(78000, 1)

    def test_accessory_catalog_covers_unverified(self):
        from els_server.domain.gm_item_catalog import entries
        self.assertGreater(len(list(entries())), 4000)

    def test_tier_circuits_are_grantable(self):
        from els_server.domain.gm_item_catalog import entries, plan
        from els_server.storage.inventory_state import grant_items
        catalog = {row['id']: row for row in entries()}
        for template in (118590, 118602, 118614, 118626):
            self.assertEqual(catalog[template]['group'], 1)
        item = plan(118590, 1)
        self.assertEqual((item['group'], item['metadata']), (1, 1))
        with closing(sqlite3.connect(self.path)) as db, db:
            grants = grant_items(db, [item], 1001)
        self.assertEqual(grants[0]['template'], 118590)
        self.assertEqual(grants[0]['group'], 1)


if __name__ == '__main__':
    unittest.main()
