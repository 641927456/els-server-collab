"""Exercise native preview/use through Application with private temporary saves."""
import collections
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

HOME = Path(__file__).resolve().parent
CHANNEL = sys.argv[1]
binding = next(r for r in json.loads((HOME / 'candidate-manifest.json').read_bytes())['files'] if r['channel'] == CHANNEL)
sys.dont_write_bytecode = True
sys.path.insert(0, binding['base'])
import els_server.storage
els_server.storage.__path__.insert(0, str(Path(binding['candidate']).parent))
os.environ['ELS_OWNED_BOX_TEST_RUNTIME'] = binding['base']
fixture = Path('G:/els/analysis/owned-box-opening-20261031-v1/source/references/owned-box-opening-20261031-v2/test_boxes.py')
spec = importlib.util.spec_from_file_location('owned_fixture', fixture)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
TEMP = HOME / 'test-temp' / CHANNEL
TEMP.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(TEMP)
os.environ['TMP'] = os.environ['TEMP'] = str(TEMP)

from els_server.domain.growth_guide_boxes import boxes, outputs_for
from els_server.domain.inventory_items import VERIFIED_TEMPLATES
from els_server.protocol.protocol_codec import Event, encode_event
from els_server.storage.inventory_state import load_items
from els_server.storage.local_state import LocalState
from els_server.domain.local_session import LocalAccount
import els_server.storage.growth_guide_boxes as target

assert Path(target.__file__).resolve() == Path(binding['candidate']).resolve()
ROWS = []


def totals(items):
    result = collections.Counter()
    for item in items:
        result[item['template']] += item['count']
    return result


class PotionBoxes(base.Boxes):
    def setUp(self):
        super().setUp()
        self.s.enter_town = True
        self.s.pending_map = self.s.active_map
        self.s.dungeon_return_pending = False
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE location SET town=? WHERE uid=?', (self.s.active_map, self.uid))
        self.account.location = self.account.store.load()

    def grant(self, template, count=1):
        # Seed only synthetic pre-existing inventory in this private temporary save.
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            items = load_items(db, self.uid)
            slot = next(n for n in range(1000) if not any(i['group'] == 4 and i['slot'] == n for i in items))
            uid = db.execute('SELECT next_uid FROM inventory_sequence WHERE id=1').fetchone()[0]
            db.execute('UPDATE inventory_sequence SET next_uid=? WHERE id=1', (uid + 1,))
            db.execute('INSERT INTO inventory_items VALUES (?,?,?,?,?,?,?)',
                       (uid, self.uid, template, VERIFIED_TEMPLATES[template], count, 4, slot))
            return next(i for i in load_items(db, self.uid) if i['uid'] == uid)

    def send(self, item, count=1, choices=(), sequence=100, flags=(0, 0, 0)):
        payload = struct.pack('>QBBBI', item['uid'], *flags, len(choices))
        payload += b''.join(struct.pack('>i', t) for t in choices) + struct.pack('>i', count)
        return self.s.handle(Event(0x202, performers=(0,), kind=0x196, payload=payload), sequence)

    def failed(self, item, **kwargs):
        before = self.snapshot()
        answer = self.send(item, **kwargs)
        self.assertNotEqual(struct.unpack_from('>i', base.ack(answer, 0x197).payload)[0], 0)
        self.assertEqual(self.snapshot(), before)

    def exercise(self, template):
        item = self.grant(template, 2)
        event = Event(0x202, performers=(0,), kind=0x559,
                      payload=struct.pack('>iIiBB', template, 1, 0, 0, 0))
        raw = base.ack(self.s.handle(event, 90), 0x55a).payload
        self.assertEqual(struct.unpack_from('>i', raw)[0], 0)
        selection, n = struct.unpack_from('>iI', raw, 13)
        entries = [struct.unpack_from('>iii', raw, 21 + 12 * k) for k in range(n)]
        choices = tuple(row[0] for row in entries[:selection])
        expected_rows = outputs_for(template, self.account.character())
        expected = collections.Counter({row['template']: row['quantity'] for row in expected_rows
                                        if not selection or row['template'] in choices})
        for k, count in enumerate((-1, 2, 2147483647)):
            self.failed(item, count=count, choices=choices, sequence=91 + k)
        self.failed(item, choices=choices, flags=(2, 0, 0), sequence=94)
        self.failed(item, choices=(2147483647,), sequence=95)
        if selection:
            self.failed(item, sequence=96)
        before = self.snapshot()
        with patch.object(target, 'encode_event', side_effect=ValueError('controlled late encoding failure')) as injected:
            answer = self.send(item, choices=choices, sequence=99)
            self.assertTrue(injected.called)
            self.assertNotEqual(struct.unpack_from('>i', base.ack(answer, 0x197).payload)[0], 0)
        self.assertEqual(self.snapshot(), before)
        foreign = self.items(self.other)
        ed = self.account.get_reward_balances()['ed']
        before_items = self.items()
        answer = self.send(item, choices=choices)
        raw_result = base.ack(answer, 0x197).payload
        self.assertEqual(struct.unpack_from('>i', raw_result)[0], 0)
        for response in answer:
            encode_event(response)
        after = self.items()
        self.assertEqual(next(i['count'] for i in after if i['uid'] == item['uid']), 1)
        delta = totals(after)
        delta.subtract(totals(before_items))
        delta[template] += 1
        self.assertEqual(+delta, expected)
        count = struct.unpack_from('>I', raw_result, 12)[0]
        displayed = collections.Counter(dict(struct.unpack_from('>ii', raw_result, 16 + 8 * k) for k in range(count)))
        self.assertEqual(displayed, expected)
        saved = self.snapshot()
        replay = self.send(item, choices=choices)
        self.assertEqual(struct.unpack_from('>i', base.ack(replay, 0x197).payload)[0], 0)
        self.assertEqual(self.snapshot(), saved)
        cold = LocalAccount(LocalState(self.path, self.uid), self.account.account_id)
        cold.enable_characters()
        self.assertEqual(cold.get_inventory_snapshot()['items'], after)
        self.assertEqual(self.items(self.other), foreign)
        self.assertEqual(self.account.get_reward_balances()['ed'], ed)
        answer = self.send(item, count=0, choices=choices, sequence=101)
        self.assertEqual(struct.unpack_from('>i', base.ack(answer, 0x197).payload)[0], 0)
        self.assertFalse(any(i['uid'] == item['uid'] for i in self.items()))
        self.failed(item, choices=choices, sequence=102)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
        ROWS.append(dict(template=template, preview=True, native_Count1=True, historical_Count0=True,
                         exact_debit_and_rewards=True, invalid_counts_no_change=True, choice_rules=True,
                         replay_no_increment=True, late_failure_rollback=True, cold_read=True))


suite = unittest.TestSuite()
for template in (721747, 721748, 721750, 720487):
    name = f'test_{template}'
    setattr(PotionBoxes, name, lambda self, t=template: self.exercise(t))
    suite.addTest(PotionBoxes(name))
result = unittest.TextTestRunner(verbosity=2).run(suite)
report = dict(ok=result.wasSuccessful(), tests=result.testsRun, rows=ROWS,
              errors=[s for _, s in result.errors], failures=[s for _, s in result.failures],
              binding=binding, shared_guide_templates=len(boxes()),
              scope='Actual Application LocalSession; private G-drive temporary SQLite; synthetic existing items',
              natural_GUI=False, installed=False, temporary_databases_cleaned=not any(TEMP.iterdir()))
(HOME / f'tests-{CHANNEL}.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(ok=report['ok'], tests=report['tests'], passed=len(ROWS), clean=report['temporary_databases_cleaned'])))
sys.exit(not result.wasSuccessful())
