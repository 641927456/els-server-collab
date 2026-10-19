"""Previously unrouted material/special/tool pages use the real 104 UI route."""
import sqlite3
import struct
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from els_server.domain.inventory_items import VERIFIED_TEMPLATES, TEMPLATE_BAG_GROUPS
from els_server.domain.local_session import LocalAccount, LocalSession
from els_server.protocol.protocol_codec import Event
from els_server.storage.inventory_state import grant_items
from els_server.storage.local_state import LocalState


class BagUiMoveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'bags.sqlite3'
        self.account = LocalAccount(LocalState(self.path))
        self.account.enable_characters()
        self.session = LocalSession(self.account, enter_town=True, enter_dungeon=True,
                                    client_build='dx11_260923', npc_slot_test=True, gate_test=True,
                                    population_test=True, clear_test=True, reward_test=True, item_test=True)
        self.session.role = 'game'
        self.session.phase = 'town_ready'

    def grant(self, template, count=1):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            return grant_items(db, [dict(template=template, quantity=count,
                                        metadata=VERIFIED_TEMPLATES[template], group=TEMPLATE_BAG_GROUPS[template])])[0]

    def action(self, kind, payload, seq=1):
        answer = self.session.handle(Event(0x202, kind=kind, payload=payload), seq)
        self.assertEqual(len(answer), 1)
        return answer[0]

    def test_material_special_and_tool_page_moves_persist(self):
        before_balance = self.account.get_reward_balances()
        for template, count in ((135983, 9), (800000, 3), (135928, 1), (77420, 5)):
            with self.subTest(template=template):
                item = self.grant(template, count)
                group = item['group']
                result = self.action(0x104, struct.pack('>BiBiB', group, item['slot'], group, 5, 0))
                self.assertEqual(result.kind, 0x105)
                self.assertEqual(result.payload[-4:], bytes(4))
                self.assertIn(dict(item, slot=5), self.account.get_inventory_snapshot()['items'])
        restored = LocalAccount(LocalState(self.path))
        self.assertEqual(restored.get_inventory_snapshot(), self.account.get_inventory_snapshot())
        self.assertEqual(self.account.get_reward_balances(), before_balance)

    def test_special_bag_swaps_keep_both_item_uids_and_counts(self):
        first = self.grant(800000, 3)
        second = self.grant(274160, 2)
        result = self.action(0x104, struct.pack('>BiBiB', 4, first['slot'], 4, second['slot'], 0))
        self.assertEqual(result.payload[-4:], bytes(4))
        items = self.account.get_inventory_snapshot()['items']
        self.assertIn(dict(first, slot=second['slot']), items)
        self.assertIn(dict(second, slot=first['slot']), items)

    def test_material_split_merge_and_partial_discard_buttons_form_one_flow(self):
        item = self.grant(135983, 10)
        split = self.action(0x555, struct.pack('>BiBii', 3, item['slot'], 3, 5, 3), 1)
        self.assertEqual(split.kind, 0x556)
        self.assertEqual(split.payload[-4:], bytes(4))
        split_item = next(i for i in self.account.get_inventory_snapshot()['items'] if i['group'] == 3 and i['slot'] == 5)
        merge = self.action(0x104, struct.pack('>BiBiB', 3, 5, 3, item['slot'], 0), 2)
        self.assertEqual(merge.payload[-4:], bytes(4))
        items = self.account.get_inventory_snapshot()['items']
        self.assertIn(item, items)
        self.assertFalse(any(i['uid'] == split_item['uid'] for i in items))
        discarded = self.action(0x109, struct.pack('>Qi', item['uid'], 2), 3)
        self.assertEqual(discarded.kind, 0x10a)
        self.assertEqual(discarded.payload[:4], bytes(4))
        self.assertIn(dict(item, count=8), self.account.get_inventory_snapshot()['items'])

    def test_cross_page_moves_still_fail_without_reclassification(self):
        item = self.grant(135983, 9)
        before = self.account.get_inventory_snapshot()
        result = self.action(0x104, struct.pack('>BiBiB', 3, item['slot'], 4, 5, 0))
        self.assertEqual(result.payload[-4:], struct.pack('>i', -1))
        self.assertEqual(self.account.get_inventory_snapshot(), before)


if __name__ == '__main__':
    unittest.main()
