"""Every catalogued permanent custom book is usable, not just the sampled ones.

The 定制 window could be opened and the native C595C0 use request carried the
custom the client believed the book granted, but the storage layer read only
the UID and demanded a zero target, so every real use was answered with
result -1 and the book stayed in the bag. This pins the whole catalogue:

  * all catalogued rules survive canonical()/custom_type()/slot_value(),
  * every book an Elsword character can actually hold registers end to end.

Evidence: state/wire-debug.log 22:51:43 and 22:53:51, `kind=0x219 len=29`
payloads `00000000000f46a2...0000000f00034969` (book 451208, custom 1000073,
family 15) and `00000000000f4675000000000000371b00000007...` (book 311328,
custom 14107, family 7).
"""
import sqlite3
import struct
import sys
import tempfile
import unittest
from collections import Counter
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from els_server.domain import character_custom as custom
from els_server.domain.inventory_items import TEMPLATE_BAG_GROUPS, VERIFIED_TEMPLATES
from els_server.domain.local_session import LocalAccount
from els_server.storage import character_custom as store
from els_server.storage.inventory_state import grant_items
from els_server.storage.local_state import LocalState

OWNER = 1001
ELSWORD = 1
THIRD_JOB = 152


def use_payload(uid, rule):
    """C595C0: UID, granted custom, its family, highlighted socket, two pads."""
    return struct.pack('>QQiiIB', uid, rule['custom_id'], rule['type'], 0, 0, 0)


class CatalogRuleTests(unittest.TestCase):
    def test_every_rule_round_trips_through_the_wire_contract(self):
        rules = custom.catalog()
        self.assertGreaterEqual(len(rules), 3200)
        problems = []
        for template, rule in rules.items():
            try:
                self.assertEqual(store._book_request(use_payload(1, rule)),
                                 (1, rule['custom_id'], rule['type'], 0))
                value = custom.canonical(rule['custom_id'])
                self.assertEqual(custom.custom_type(rule['custom_id']), rule['type'])
                custom.slot_value(rule['slot'], value)
            except Exception as error:  # noqa: BLE001 - reported per template
                problems.append((template, repr(error)))
        self.assertEqual(problems, [], problems[:10])

    def test_custom_ids_are_unique_across_the_catalogue(self):
        rules = custom.catalog()
        for family in sorted({r['type'] for r in rules.values()}):
            ids = [r['custom_id'] for r in rules.values() if r['type'] == family]
            self.assertEqual(len(ids), len(set(ids)), family)


class BookUseTests(unittest.TestCase):
    """The acting character's whole holdable book set, one use per book."""

    def test_every_holdable_book_for_the_acting_character_registers(self):
        rules = custom.catalog()
        holdable = sorted(
            (template, rule) for template, rule in rules.items()
            if rule['unit_type'] == ELSWORD and not rule.get('native_only')
            and template in VERIFIED_TEMPLATES)
        self.assertGreater(len(holdable), 200, len(holdable))

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'custom.sqlite3'
            account = LocalAccount(LocalState(path))
            account.enable_characters()
            account.get_inventory_snapshot()
            with closing(sqlite3.connect(path)) as db, db:
                db.execute('UPDATE characters SET unit_class=?,level=99 WHERE uid=?',
                           (THIRD_JOB, OWNER))

            failures = Counter()
            registered = 0
            for index, (template, rule) in enumerate(holdable):
                # Grant one at a time: a successful use consumes the book, so
                # the bag never fills and every use is a real first use.
                with closing(sqlite3.connect(path)) as db, db:
                    items = grant_items(db, [dict(template=template,
                                                  metadata=VERIFIED_TEMPLATES[template],
                                                  group=TEMPLATE_BAG_GROUPS[template],
                                                  quantity=1)])
                item = next((i for i in items if i['template'] == template), None)
                if item is None:
                    failures['not granted'] += 1
                    continue
                try:
                    receipt = store.use_book(path, OWNER, account.account_id,
                                             use_payload(item['uid'], rule),
                                             'all-books-%d-%d' % (index, template))
                except Exception as error:  # noqa: BLE001 - reported per book
                    failures[str(error)] += 1
                    continue
                if receipt is None:
                    failures['not a catalogued book'] += 1
                    continue
                self.assertEqual([e.kind for e in receipt['events']], [0x21a, 0x4cd])
                registered += 1

            self.assertEqual(failures, Counter(), failures.most_common(10))
            self.assertEqual(registered, len(holdable))
            with closing(sqlite3.connect(path)) as db:
                owned = db.execute('SELECT COUNT(*) FROM character_custom_permanent '
                                   'WHERE owner=?', (OWNER,)).fetchone()[0]
            self.assertEqual(owned, len(holdable))


class DispatchOrderTests(unittest.TestCase):
    """0x219 is one envelope: earlier families must decline, not answer -1.

    C595C0 is shared. The capacity ticket and the ERP resonance book are tried
    before the permanent custom books, and both parsed with
    career_messages.use_request(), which rejects any non-zero target. Because
    the client fills that word with the custom the book grants, the resonance
    handler used to raise and the session answered 0x21A result=-1 before the
    custom family ever ran — every custom book in the game looked "unusable".
    """

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'dispatch.sqlite3'
        account = LocalAccount(LocalState(self.path))
        account.enable_characters()
        account.get_inventory_snapshot()
        self.account = account

    def payload(self):
        rule = next(rule for rule in custom.catalog().values()
                    if rule['unit_type'] == ELSWORD and not rule.get('native_only')
                    and rule['book'] in VERIFIED_TEMPLATES)
        return rule, use_payload(1, rule)

    def test_capacity_ticket_declines_a_custom_book_request(self):
        from els_server.storage.boosting_2026_nested_capacity import use_ticket
        _, payload = self.payload()
        self.assertIsNone(use_ticket(self.path, OWNER, payload, 'dispatch-capacity'))

    def test_resonance_book_declines_a_custom_book_request(self):
        from els_server.storage.resonance_state import use_book as use_resonance_book
        _, payload = self.payload()
        self.assertIsNone(use_resonance_book(self.path, OWNER, self.account.account_id,
                                             payload, 'dispatch-resonance'))

    def test_the_custom_book_still_answers_after_the_declines(self):
        rule, payload = self.payload()
        with closing(sqlite3.connect(self.path)) as db, db:
            items = grant_items(db, [dict(template=rule['book'],
                                          metadata=VERIFIED_TEMPLATES[rule['book']],
                                          group=TEMPLATE_BAG_GROUPS[rule['book']],
                                          quantity=1)])
        uid = next(i['uid'] for i in items if i['template'] == rule['book'])
        receipt = store.use_book(self.path, OWNER, self.account.account_id,
                                 use_payload(uid, rule), 'dispatch-custom')
        self.assertEqual([e.kind for e in receipt['events']], [0x21a, 0x4cd])


if __name__ == '__main__':
    unittest.main()
