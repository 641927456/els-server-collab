"""The four remaining Boost containers and the event deadline they share.

The 2026-11-01 delivery left these four boxes unread, so holding one produced a
silent 0x197 refusal. owned_reward_boxes now reads them from the same published
contents as the other 科宝 boxes, their contents are event capped at
local-growth.json configuration.ends, and none of them may enter the shared
bank.
"""
import sqlite3
import struct
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from els_server.domain import owned_reward_boxes
from els_server.domain.bank_rules import require_storable
from els_server.domain.boosting_2026_item_policy import EVENT_ITEMS, deadline, item_deadline
from els_server.domain.inventory_items import TEMPLATE_BAG_GROUPS, VERIFIED_TEMPLATES
from els_server.domain.item_expiration import expired
from els_server.domain.local_session import LocalAccount
from els_server.storage import fixed_cubes
from els_server.storage.inventory_state import grant_items, load_items
from els_server.storage.local_state import LocalState

# Container -> exact published contents, in native order.
CONTENTS = {
    723619: [(710128, 30), (118653, 30)],
    723620: [(723622, 5), (723623, 5), (723624, 5), (723625, 5)],
    723621: [(30675, 1), (30676, 1), (30677, 1)],
    723634: [(30770, 1), (30771, 1), (30772, 1), (30773, 1), (30832, 1)],
}
CHARACTER = {'unit_type': 1, 'unit_class': 152, 'level': 99, 'transcendence': True, 'master': False}


def wire(uid):
    return struct.pack('>QBBBIi', uid, 0, 0, 0, 0, 0)


class CatalogTests(unittest.TestCase):
    def test_the_four_containers_join_the_owned_reward_set(self):
        boxes = {row['template'] for row in owned_reward_boxes.catalog()['boxes']}
        self.assertEqual(boxes, {117542, 135666, 135871, 723618, 723619, 723620,
                                 723621, 723634, 723687, 723688, 980047})

    def test_each_container_answers_with_its_published_contents(self):
        for template, expected in CONTENTS.items():
            outputs = owned_reward_boxes.outputs_for(template, CHARACTER)
            self.assertEqual([(o['template'], o['quantity']) for o in outputs], expected, template)
            self.assertEqual(owned_reward_boxes.selected_outputs(template, CHARACTER, ()), outputs)

    def test_every_output_template_is_registered_for_its_native_bag(self):
        readers = {row['template']: row for row in owned_reward_boxes.catalog()['readers']}
        for outputs in CONTENTS.values():
            for template, _ in outputs:
                self.assertIn(template, VERIFIED_TEMPLATES)
                self.assertEqual(TEMPLATE_BAG_GROUPS[template], readers[template]['group'], template)

    def test_all_four_are_event_containers(self):
        for template in CONTENTS:
            self.assertIn(template, EVENT_ITEMS)


class OpeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'game.sqlite3'
        LocalAccount(LocalState(self.path)).enable_characters()

    def grant(self, template):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            with patch('els_server.domain.acquisition_policy.require_acquirable', lambda *a, **k: None):
                return grant_items(db, [dict(template=template,
                    metadata=VERIFIED_TEMPLATES[template],
                    group=TEMPLATE_BAG_GROUPS[template], quantity=1)], 1001)[0]

    def open(self, template, uid):
        return fixed_cubes.open_cube(self.path, 1001, template, wire(uid),
                                     'activities-' + str(template), account_id=1,
                                     prepare=lambda db: None)

    def snapshot(self):
        with closing(sqlite3.connect(self.path)) as db:
            return load_items(db, 1001)

    def test_each_container_opens_once_and_grants_every_line(self):
        for template, expected in CONTENTS.items():
            box = self.grant(template)
            events = self.open(template, box['uid'])
            self.assertEqual([e.kind for e in events], [0xad8, 0x197], template)
            self.assertEqual(struct.unpack_from('>iiiI', events[-1].payload)[:3], (0, 0, 0))
            self.assertNotIn(box['uid'], {i['uid'] for i in self.snapshot()}, template)
            owned = {(i['template'], i['count']) for i in self.snapshot()}
            for line in expected:
                self.assertIn(line, owned, template)

    def test_the_same_operation_is_not_granted_twice(self):
        box = self.grant(723621)
        self.open(723621, box['uid'])
        counts = sorted((i['template'], i['count']) for i in self.snapshot())
        replay = fixed_cubes.open_cube(self.path, 1001, 723621, wire(box['uid']),
                                       'activities-723621', account_id=1,
                                       prepare=lambda db: None)
        # The replayed request answers from the stored receipt: it reports the
        # already applied inventory change, never a second grant.
        self.assertEqual(replay[-1].kind, 0x197)
        self.assertEqual(struct.unpack_from('>iiiI', replay[-1].payload)[:3], (0, 0, 0))
        self.assertEqual(sorted((i['template'], i['count']) for i in self.snapshot()), counts)


class EventDeadlineTests(unittest.TestCase):
    def test_a_plain_item_keeps_its_own_lifetime(self):
        self.assertIsNone(item_deadline({'template': 60100}))
        self.assertEqual(item_deadline({'template': 60100, 'expires_at': 1_800_000_000}), 1_800_000_000)

    def test_an_event_item_is_capped_at_the_configured_end(self):
        end = deadline()
        self.assertEqual(item_deadline({'template': 723621}), end)
        self.assertEqual(item_deadline({'template': 723621, 'expires_at': end + 10**6}), end)
        self.assertEqual(item_deadline({'template': 723621, 'expires_at': end - 10}), end - 10)

    def test_the_event_is_still_open_today(self):
        self.assertFalse(expired({'template': 723621}))
        self.assertTrue(expired({'template': 723621}, now=deadline() + 1))
        self.assertFalse(expired({'template': 723621}, now=deadline() - 1))


class SharedBankTests(unittest.TestCase):
    def test_an_event_container_cannot_enter_the_shared_bank(self):
        with self.assertRaises(ValueError):
            require_storable({'template': 723621, 'group': 4}, 16)

    def test_a_normal_container_is_still_allowed(self):
        require_storable({'template': 117542, 'group': 4}, 16)


if __name__ == '__main__':
    unittest.main()
