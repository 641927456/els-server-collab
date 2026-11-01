"""Native 219 quantity requests must reach the owned Artifact consumer."""
import json
import sqlite3
import struct
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from els_server.domain import artifact_progression as rules
from els_server.domain.local_session import LocalAccount, LocalSession
from els_server.protocol.protocol_codec import Event
from els_server.storage import artifact_progression as storage
from els_server.storage.inventory_state import grant_items
from els_server.storage.local_state import LocalState


class ArtifactGrowthRoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'qa.sqlite3'
        self.account = LocalAccount(LocalState(self.path))
        self.account.enable_characters()
        self.stage(1)
        self.session = LocalSession(self.account, enter_town=True, client_build='dx11_260923')
        self.session.item_test = True
        self.session.phase = 'town_ready'
        self.session.role = 'game'

    def stage(self, stage):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE characters SET unit_class=150,level=99,transcendence=1,master=1 WHERE uid=1001')
            db.execute('INSERT OR REPLACE INTO character_artifacts VALUES (1001,1,?,1,0,?)', (stage, json.dumps([0]*4)))

    def grant(self, template, count):
        row = next(r for r in rules.catalog()['definitions'] if r['template'] == template)
        with closing(sqlite3.connect(self.path)) as db, db:
            return grant_items(db, [dict(template=template, metadata=row['metadata'], group=row['group'], quantity=count)], 1001)[0]

    def send(self, item, count, sequence=1):
        payload = struct.pack('>QQiiIB', item['uid'], count, 0, 0, 0, 0)
        return self.session.handle(Event(0x202, kind=0x219, payload=payload), sequence)

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db:
            return list(db.iterdump())

    def assert_success(self, events):
        self.assertEqual([e.kind for e in events], [0x21a, 0x904])
        self.assertEqual(struct.unpack_from('>i', events[0].payload)[0], 0)

    def test_ariel_explicit_one_and_bulk_commit_cold_read_and_replay(self):
        item = self.grant(711317, 3)
        self.assert_success(self.send(item, 1))
        self.assertEqual(self.account.character()['artifact']['level'], 2)
        self.assert_success(self.send(item, 2, 2))
        cold = LocalAccount(LocalState(self.path))
        cold.enable_characters()
        self.assertEqual(cold.character()['artifact']['level'], 4)
        self.assertNotIn(item['uid'], [i['uid'] for i in cold.get_inventory_snapshot()['items']])
        before = self.dump()
        self.assert_success(self.send(item, 2, 2))
        self.assertEqual(before, self.dump())

    def test_all_scroll_variants_and_potions_use_quantity_consumer(self):
        for template in rules.catalog()['level_up_items'] + [int(t) for t in rules.catalog()['exp_potions']]:
            with self.subTest(template=template):
                self.stage(1)
                item = self.grant(template, 2)
                self.assert_success(self.send(item, 2, template))
                artifact = self.account.character()['artifact']
                if template in rules.catalog()['level_up_items']:
                    self.assertEqual(artifact['level'], 3)
                else:
                    self.assertEqual(artifact['experience'], 60000000)

    def test_stage_two_transition_and_stage_three_rejection(self):
        self.stage(2)
        item = self.grant(711317, 10)
        self.assert_success(self.send(item, 9))
        self.assertEqual(self.account.character()['artifact']['evolution'], 3)
        before = self.dump()
        events = self.send(item, 1, 2)
        self.assertEqual(struct.unpack_from('>i', events[0].payload)[0], 2005)
        self.assertEqual(before, self.dump())

    def test_insufficient_count_and_encoding_failure_are_atomic(self):
        item = self.grant(711317, 2)
        before = self.dump()
        events = self.send(item, 3)
        self.assertEqual(struct.unpack_from('>i', events[0].payload)[0], 2005)
        self.assertEqual(before, self.dump())
        payload = struct.pack('>QQiiIB', item['uid'], 2, 0, 0, 0, 0)
        with self.assertRaisesRegex(RuntimeError, 'encode failed'):
            storage.action(self.path, 1001, 'potion', payload, 'failed-encode', account_id=1,
                           encode=lambda _: (_ for _ in ()).throw(RuntimeError('encode failed')))
        self.assertEqual(before, self.dump())

    def test_plain_click_and_other_consumers_keep_their_dispatch(self):
        item = self.grant(711317, 1)
        self.assert_success(self.send(item, 0))
        self.assertEqual(self.account.character()['artifact']['level'], 2)
        # A non-Artifact request still reaches the next existing consumer.
        payload = struct.pack('>QQiiIB', 123456789, 0, 0, 0, 0, 0)
        reply = Event(0x201, kind=0x21a, payload=bytes(36))
        with patch('els_server.storage.boosting_2026_nested_capacity.use_ticket', return_value=None), \
             patch('els_server.storage.resonance_state.use_book', return_value=dict(events=[reply], replayed=False)) as resonance, \
             patch.object(self.session, 'saved_user_sync', return_value=reply):
            self.session.handle(Event(0x202, kind=0x219, payload=payload), 2)
        resonance.assert_called_once()


if __name__ == '__main__':
    unittest.main()
