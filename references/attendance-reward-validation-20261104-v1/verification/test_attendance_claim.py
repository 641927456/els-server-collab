"""Synthetic fixture only; imports pinned runtime plus the one-file candidate."""
import json
import os
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ARCHIVE = HERE.parent
BASE = Path(os.environ['ELS_ATTENDANCE_TEST_BASE']).resolve()
TEMP = Path(os.environ['ELS_ATTENDANCE_TEST_TEMP']).resolve();TEMP.mkdir(parents=True,exist_ok=True)
import atexit
_overlay = tempfile.TemporaryDirectory(dir=TEMP);atexit.register(_overlay.cleanup)
CANDIDATE = Path(_overlay.name)
for package in ('els_server','els_server/domain'):
    directory=CANDIDATE/package;directory.mkdir(parents=True,exist_ok=True)
    (directory/'__init__.py').write_text('from pathlib import Path\n__path__=[str(Path(__file__).parent),'+repr(str(BASE/package))+']\n','utf8')
(CANDIDATE/'els_server/domain/inventory_items.py').write_bytes((ARCHIVE/'source/online/els_server/domain/inventory_items.py').read_bytes())
(CANDIDATE/'els_server/data').mkdir()
(CANDIDATE/'els_server/data/special_task_readers.json').write_bytes((BASE/'els_server/data/special_task_readers.json').read_bytes())
sys.path.insert(0,str(CANDIDATE))
HERE = TEMP

from els_server.domain import inventory_items as items
from els_server.domain.selected_2026_pair_runtime import SelectedAttendanceOnline
from els_server.domain.retained_native_consumables import TEMPLATES, read_existing
from els_server.storage.mail_attachments import _snapshot, pending


def manager(path):
    directory = BASE/'els_server/data/selected2026'
    pack = json.loads((directory/'local-pair.json').read_bytes())
    return SelectedAttendanceOnline(path, pack['configuration'], {
        key: (directory/row['file']).read_bytes()
        for key, row in pack['resources'].items()
    })


class AttendanceClaimTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manager = manager(HERE/'unused.db')
        cls.manager.catalog.register_inventory()

    def fixture(self):
        directory = tempfile.TemporaryDirectory(dir=HERE)
        self.addCleanup(directory.cleanup)
        path = Path(directory.name)/'synthetic.sqlite3'
        db = sqlite3.connect(path)
        self.addCleanup(db.close)
        db.executescript('''
            CREATE TABLE characters(uid INTEGER PRIMARY KEY,level INTEGER);
            CREATE TABLE character_owners(uid INTEGER PRIMARY KEY,account_id INTEGER);
            CREATE TABLE reward_balances(uid INTEGER PRIMARY KEY,ed INTEGER,experience INTEGER,revision INTEGER);
            CREATE TABLE inventory_sequence(id INTEGER PRIMARY KEY,next_uid INTEGER);
            CREATE TABLE inventory_items(uid INTEGER PRIMARY KEY);
            INSERT INTO characters VALUES(1001,99);
            INSERT INTO character_owners VALUES(1001,1);
            INSERT INTO reward_balances VALUES(1001,100,0,1);
            INSERT INTO inventory_sequence VALUES(1,50001);
        ''')
        task = self.manager._attendance(db)
        task.progress.initialize()
        self.manager.schedule.install(task.progress)
        task.initialize()
        # The affected day is index15, before the CN10:00 reset on Nov4.
        now = self.manager.schedule.periods[15].starts + 7200
        task.accept(account=1, character=1001, now=now-3600)
        # Server-authoritative ready fixture: OR condition, three clears.
        with db:
            db.execute('UPDATE activity518_tasks SET clears=3,seconds=3600,ready_at=?', (now,))
        return path, db, task, now

    def test_all_42_approved_reward_attachments_serialize(self):
        overlap = set()
        for rid in range(8127,8169):
            for row in self.manager.catalog.plan(rid):
                template = row['template']
                if template in TEMPLATES:
                    overlap.add(template)
                item = dict(uid=50001,template=template,metadata=row['metadata'],
                            group=row['group'],slot=0,count=row['quantity'])
                with self.subTest(reward=rid,template=template):
                    self.assertEqual(json.loads(_snapshot(item)),item)
        self.assertIn(716611,overlap)
        print('registered reward/retained overlap:', sorted(overlap))

    def test_complete_online_or_condition_claim_replay_and_cold_read(self):
        path, db, task, now = self.fixture()
        first = task.claim(account=1,character=1001,now=now,operation='owned-claim',encode=lambda out:b'OK')
        self.assertFalse(first['replayed'])
        self.assertIsNone(task._read(1))
        attachment = pending(db,first['mail_id'],now=now)
        self.assertEqual((attachment['template'],attachment['count']),(716611,1))
        replay = task.claim(account=1,character=1001,now=now,operation='owned-claim',encode=lambda out:b'OK')
        self.assertTrue(replay['replayed'])
        self.assertEqual(first['mail_id'],replay['mail_id'])
        with closing(sqlite3.connect(path)) as cold:
            for table in ('activity518_stamps','activity2026_reward_deliveries','game_mail','player_mail_items'):
                self.assertEqual(cold.execute('SELECT count(*) FROM '+table).fetchone()[0],1)
            self.assertEqual(cold.execute('SELECT next_uid FROM inventory_sequence').fetchone()[0],50002)
            self.assertEqual(cold.execute('SELECT ed FROM reward_balances').fetchone()[0],100)

    def test_encoder_failure_rolls_back_mail_stamp_task_and_sequence(self):
        path, db, task, now = self.fixture()
        before = list(db.iterdump())
        def fail(out):
            raise ValueError('synthetic encoder failure')
        with self.assertRaisesRegex(ValueError,'synthetic encoder failure'):
            task.claim(account=1,character=1001,now=now,operation='owned-failure',encode=fail)
        self.assertEqual(list(db.iterdump()),before)
        task.claim(account=1,character=1001,now=now,operation='owned-failure',encode=lambda out:b'OK')
        self.assertEqual(db.execute('SELECT count(*) FROM game_mail').fetchone()[0],1)

    def test_incomplete_and_wrong_owner_claims_do_not_mutate(self):
        path, db, task, now = self.fixture()
        with db:
            db.execute('UPDATE activity518_tasks SET seconds=0,clears=0,ready_at=NULL')
        before = list(db.iterdump())
        for account in (1,2):
            with self.assertRaises(ValueError):
                task.claim(account=account,character=1001,now=now,operation='rejected',encode=lambda out:b'OK')
            self.assertEqual(list(db.iterdump()),before)

    def test_unapproved_native_item_and_invalid_approved_instances_stay_rejected(self):
        from els_server.domain.acquisition_policy import can_acquire
        self.assertFalse(can_acquire(716611))
        denied = next(t for t in sorted(TEMPLATES) if t not in items.VERIFIED_TEMPLATES)
        definition = __import__('els_server.domain.retained_native_consumables',fromlist=['definitions']).definitions()[denied]
        sample = dict(uid=50001,template=denied,metadata=definition['metadata'],group=definition['group'],slot=0,count=1)
        with self.assertRaisesRegex(ValueError,'Unchanged owned native consumable reader required'):
            items.validate_item(sample)
        existing = read_existing(sample)
        self.assertEqual(items.validate_item(existing),sample)
        existing['uid'] += 1
        with self.assertRaises(ValueError):
            items.validate_item(existing)
        approved = dict(uid=50002,template=716611,metadata=0,group=4,slot=0,count=1)
        for change in (dict(metadata=2),dict(group=6),dict(count=0),dict(slot=-1)):
            with self.assertRaises(ValueError):
                items.validate_item(dict(approved,**change))


if __name__ == '__main__':
    unittest.main(verbosity=2)
