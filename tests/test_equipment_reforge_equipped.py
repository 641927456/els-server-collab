import sqlite3, struct, tempfile, unittest
from contextlib import closing
from pathlib import Path
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState


class EquippedReforgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'state.sqlite3'
        self.account = LocalAccount(LocalState(self.path)); self.account.enable_characters()

    def test_equipped_armor_can_be_reforged(self):
        from els_server.domain.equipment_reforge_rules import DEFAULT, demand, catalog
        from els_server.storage.equipment_reforge import perform
        target, material = 119241, 119210
        requirements, _ = demand(target, DEFAULT, material)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE reward_balances SET ed=10000000 WHERE uid=1001')
            db.execute('INSERT INTO inventory_items VALUES (900001,1001,?,1,1,9,1)', (target,))
            rows = [(900002 + index, 1001, template, catalog()['materials'][str(template)]['metadata'],
                     quantity, catalog()['materials'][str(template)]['group'], index)
                    for index, (template, quantity) in enumerate(requirements.items())]
            db.executemany('INSERT INTO inventory_items VALUES (?,?,?,?,?,?,?)', rows)
        payload = struct.pack('>QiBB', 900001, material, 0, 0)
        events = perform(self.path, 1001, payload, 'equipped-reforge-test', restoration=False, account_id=1)
        self.assertEqual([event.kind for event in events], [0x8d6])
        self.assertEqual(struct.unpack_from('>i', events[0].payload)[0], 0)


if __name__ == '__main__':
    unittest.main()
