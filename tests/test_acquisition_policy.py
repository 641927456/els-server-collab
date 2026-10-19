import sqlite3, tempfile, unittest
from pathlib import Path
from contextlib import closing
from els_server.domain.acquisition_policy import has_legacy_marker, excluded_equipment, can_acquire
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items, load_items, validate_plan
from els_server.domain.inventory_items import item_body, VERIFIED_TEMPLATES, TEMPLATE_BAG_GROUPS
from tests.historical_inventory import seed_existing_items


class AcquisitionPolicyTests(unittest.TestCase):
    def test_explicit_marker_and_current_templates(self):
        for name in ('（旧）武器','武器(旧)','（舊）武器','武器( 旧 )'):
            self.assertTrue(has_legacy_marker(name))
        for name in ('破旧长剑','怀旧套装','新武器'):
            self.assertFalse(has_legacy_marker(name))
        self.assertIn(100,excluded_equipment())
        self.assertTrue(can_acquire(60100))
        self.assertTrue(can_acquire(30388))
        for template in excluded_equipment() & VERIFIED_TEMPLATES.keys():
            with self.assertRaisesRegex(ValueError,'Legacy equipment acquisition disabled'):
                validate_plan([dict(template=template,metadata=VERIFIED_TEMPLATES[template],group=TEMPLATE_BAG_GROUPS[template],quantity=1)])

    def test_all_live_offers_and_role_pools_are_current(self):
        from els_server.storage.shop_state import catalog,home_lists
        from els_server.domain.ice_rules import role_pools
        from els_server.domain.drop_pickup import GROUND_TEMPLATES
        self.assertTrue(all(can_acquire(t) for t in GROUND_TEMPLATES))
        for unit in range(1,16):
            offered={p['template'] for p in catalog(unit)}
            self.assertTrue(all(can_acquire(t) for t in offered))
            self.assertTrue(all(t in offered for group in home_lists(unit) for t in group))
            self.assertTrue(all(can_acquire(t) for pool in role_pools(unit).values() for t,_ in pool))

    def test_mixed_grant_rejected_before_mutation_existing_items_still_load(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'save.db';a=LocalAccount(LocalState(path));a.enable_characters()
            old=dict(template=100,metadata=1,quantity=1,group=1)
            current=dict(template=60100,metadata=1,quantity=1,group=1)
            with closing(sqlite3.connect(path)) as db,db:
                seed_existing_items(db,[old])
            with closing(sqlite3.connect(path)) as db,db:
                before=list(db.iterdump());db.execute('BEGIN IMMEDIATE')
                with self.assertRaises(ValueError):grant_items(db,[current,old])
                self.assertEqual(before,list(db.iterdump()))
                saved=load_items(db);self.assertEqual(saved[0]['template'],100)
                self.assertEqual(len(item_body(saved[0])),304)
                new=grant_items(db,[current])[0];self.assertEqual(new['template'],60100)
            self.assertEqual({i['template'] for i in a.get_inventory_snapshot()['items']},{100,60100})

    def test_reward_balance_and_receipt_roll_back_for_legacy_item(self):
        import uuid
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'save.db';a=LocalAccount(LocalState(path));a.enable_characters()
            before=a.get_inventory_snapshot();run=str(uuid.uuid4())
            with self.assertRaisesRegex(ValueError,'Legacy equipment acquisition disabled'):
                a.reward_store.grant(run,b'clear',120,50,lambda _:b'ok',
                    item_plan=[dict(template=100,metadata=1,group=1,quantity=1)])
            self.assertEqual(a.get_inventory_snapshot(),before)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM reward_receipts WHERE run_id=?',(run,)).fetchone()[0],0)
