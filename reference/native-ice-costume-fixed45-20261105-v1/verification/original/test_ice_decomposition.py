"""Isolated current-server tests for the owner's fixed-45 ice costume rule."""
import collections
import hashlib
import json
import sqlite3
import struct
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from pathlib import Path

WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[1]
BASE = ROOT/'releases/online/native-market-progress-20261105-v1'
CANDIDATE = WORK/'candidate'
sys.dont_write_bytecode = True
sys.path.insert(0, str(BASE))
import els_server.domain
els_server.domain.__path__.insert(0, str(CANDIDATE/'els_server/domain'))

from els_server.domain.decomposition_rules import quote, reward_definition
from els_server.domain.ice_decomposition import templates
from els_server.domain.inventory_items import (
    VERIFIED_TEMPLATES, TEMPLATE_BAG_GROUPS, TEMPLATE_MAX_STACKS, FASHION_EQUIP_SLOTS)
from els_server.domain.local_session import LocalAccount, LocalSession
from els_server.domain.white_chip_decomposition_flow import handle
from els_server.game_data import client_data
from els_server.protocol.protocol_codec import Event
from els_server.protocol.profession_messages import ProfessionState
from els_server.storage.characters import Characters
from els_server.storage.decomposition import decompose
from els_server.storage.inventory_state import ensure_inventory, grant_items, load_items
from els_server.storage.local_state import LocalState, ensure_local_tables
from els_server.storage.reward_state import ensure_reward_tables

EVIDENCE = {}


def request(*uids):
    return struct.pack('>I', len(uids))+b''.join(struct.pack('>Q', u) for u in uids)+b'\0'


def base_item(t):
    return dict(uid=900000+t, template=t, metadata=VERIFIED_TEMPLATES[t],
                group=TEMPLATE_BAG_GROUPS[t], slot=0, count=1)


def rewards(wire):
    count = struct.unpack_from('>I', wire, 5)[0]
    return dict(struct.unpack_from('>ii', wire, 9+8*i) for i in range(count))


class IceDecomposition(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='fixed45-owned-', dir=WORK)
        self.path = Path(self.tmp.name)/'save.sqlite3'
        with self.db() as db:
            ensure_local_tables(db)
            ensure_reward_tables(db)
            ensure_inventory(db)
        self.characters = Characters(self.path, 1)
        self.uid = self.characters.create('FixedIce', 1, 'create-fixed45')['uid']
        self.account = LocalAccount(LocalState(self.path, self.uid), 1, 'isolated-fixed45')
        self.account.enable_characters(characters=self.characters)

    def tearDown(self):
        self.tmp.cleanup()

    @contextmanager
    def db(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE')
            yield db

    def grant(self, t, quantity=1):
        with self.db() as db:
            return grant_items(db, [dict(template=t, metadata=VERIFIED_TEMPLATES[t],
                group=TEMPLATE_BAG_GROUPS[t], quantity=quantity)], self.uid)[0]

    def items(self):
        with closing(sqlite3.connect(self.path)) as db:
            return load_items(db, self.uid)

    def totals(self):
        result = collections.Counter()
        for item in self.items():
            result[item['template']] += item['count']
        return result

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db:
            return list(db.iterdump())

    def perform(self, items, operation='decompose', **kwargs):
        return decompose(self.path, self.uid, request(*(i['uid'] for i in items)),
                         operation, account_id=1, **kwargs)

    def session(self):
        return LocalSession(self.account, client_build='dx11_260923',
            enter_dungeon=True, npc_slot_test=True, gate_test=True,
            population_test=True, clear_test=True, reward_test=True, item_test=True)

    def native(self, response, expected_reward):
        sys.path.insert(0, str(ROOT/'tools'))
        from verify_inventory_management_native import ManagementReplay
        actual = ManagementReplay().management('decompose', response[0].payload)
        self.assertEqual(actual['result'], 0)
        self.assertEqual(rewards(response[0].payload), expected_reward)
        # Original reader consumes the whole ACK and exposes actual item records.
        for t, n in expected_reward.items():
            actual_count = sum(row['count'] for row in actual['rows'] if row['template'] == t)
            stored_count = self.totals()[t]
            self.assertEqual(actual_count, stored_count)
        EVIDENCE[self._testMethodName] = actual

    def test_catalog_and_legal_rejections(self):
        from els_server.domain.modern_ice import catalog
        modern = {t for box in catalog()['boxes'].values() for t in box['outputs'].values()}
        self.assertEqual(len(modern), 11520)
        self.assertTrue(modern <= templates())
        self.assertEqual(len(templates()), 11537)
        for t in templates():
            q = quote(base_item(t))
            self.assertEqual((q['template'], q['quantity']), (130047, 45))
        self.assertEqual(reward_definition(130047),
                         dict(template=130047, metadata=2, group=4, max_stack=999))
        ice = base_item(800018)
        cases = [dict(ice, sealed=True), dict(ice, expires_at=2200000000),
                 dict(ice, expires_at=1000000000), dict(ice, lock_until=2200000000),
                 dict(ice, group=9, slot=FASHION_EQUIP_SLOTS[800018]),
                 base_item(800000), base_item(800006), base_item(130047)]
        non_ice = next(t for t in FASHION_EQUIP_SLOTS
                       if t not in templates() and TEMPLATE_BAG_GROUPS[t] == 7)
        cases.append(base_item(non_ice))
        for item in cases:
            with self.subTest(item=item), self.assertRaises(ValueError):
                quote(item)
        EVIDENCE['catalog'] = dict(modern=11520, all_known=11537, rejected=len(cases))

    def test_draw_open_dispatch_and_cold_read(self):
        from els_server.storage.ice_state import draw
        from els_server.storage import modern_ice
        def use(item):
            return struct.pack('>QBBBIi', item['uid'], 0, 0, 0, 0, 0)
        machine = self.grant(800000)
        draw(self.path, use(machine), 'draw-machine', uid=self.uid, account_id=1,
             prepare=lambda db: None, randbelow=lambda total: 0)
        with self.db() as db:
            box = modern_ice.bag_items(db, 1)[0]
        self.assertEqual(box['template'], 800006)
        modern_ice.withdraw(self.path, self.uid, 1, struct.pack('>IQi', 1, box['uid'], 1),
                            'withdraw-box', lambda db: None)
        cube = next(i for i in self.items() if i['template'] == 800006)
        modern_ice.open_box(self.path, self.uid, 800006, use(cube), 'open-box',
                            account_id=1, prepare=lambda db: None)
        ice = next(i for i in self.items() if i['template'] == 800018)
        with self.db() as db:
            from els_server.storage.profession_state import replace, snapshot
            replace(db, self.uid, 1, 0, ProfessionState(2, 1, 0, {}, 0, 800))
            profession = snapshot(db, self.uid, 1)
            balance = db.execute('SELECT * FROM reward_balances').fetchall()
        s = self.session()
        s.role = 'game'
        s.phase = 'town_ready'
        event = Event(0x202, kind=0x1c0, payload=request(ice['uid']))
        response = handle(s, event, 101)
        self.native(response, {130047: 45})
        self.assertFalse(any(i['uid'] == ice['uid'] for i in self.items()))
        self.assertEqual(self.totals()[130047], 45)
        with self.db() as db:
            self.assertEqual(snapshot(db, self.uid, 1), profession)
            self.assertEqual(db.execute('SELECT * FROM reward_balances').fetchall(), balance)
        before = self.dump()
        replay = handle(s, event, 101)
        self.assertEqual(struct.unpack_from('>i', replay[0].payload)[0], 0)
        self.assertEqual(rewards(replay[0].payload), {})
        self.assertEqual(self.dump(), before)
        EVIDENCE['draw_open_dispatch'] = dict(shards=45, xp_unchanged=True,
            balances_unchanged=True, real_saved_user_sync_replay=True)

    def test_batch_merges_and_splits_native_stacks(self):
        self.grant(130047, 990)
        ice = [self.grant(800018) for _ in range(24)]
        response = self.perform(ice)
        self.native(response, {130047: 1080})
        stacks = [i['count'] for i in self.items() if i['template'] == 130047]
        self.assertEqual(sorted(stacks), [72, 999, 999])
        self.assertFalse(any(i['uid'] in {x['uid'] for x in ice} for i in self.items()))

    def test_mixed_ordinary_chip_and_ice_keep_distinct_rewards(self):
        items = [self.grant(t) for t in (30160, 118638, 800018)]
        response = self.perform(items)
        self.native(response, {701000: 36, 118445: 20, 130047: 45})
        self.assertEqual({t: self.totals()[t] for t in (701000, 118445, 130047)},
                         {701000: 36, 118445: 20, 130047: 45})

    def test_concurrent_retry_only_grants_once_and_conflict_is_atomic(self):
        ice = self.grant(800018)
        with ThreadPoolExecutor(max_workers=2) as workers:
            responses = list(workers.map(lambda _: self.perform([ice], 'same-operation'), range(2)))
        self.assertEqual(sorted(len(rewards(r[0].payload)) for r in responses), [0, 1])
        self.assertEqual(self.totals()[130047], 45)
        before = self.dump()
        self.perform([ice], 'same-operation')
        self.assertEqual(self.dump(), before)
        with self.assertRaisesRegex(ValueError, 'owned items'):
            self.perform([ice], 'new-operation-old-uid')
        replacement = self.grant(800018)
        before = self.dump()
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            self.perform([replacement], 'same-operation')
        self.assertEqual(self.dump(), before)

    def test_full_special_bag_and_encoding_failure_roll_back_all_state(self):
        from els_server.storage.bag_capacity import allowances
        ice = self.grant(800018)
        before = self.dump()
        def fail_encoding(*args, **kwargs):
            raise ValueError('injected ACK encoding failure')
        with self.assertRaisesRegex(ValueError, 'injected ACK'):
            self.perform([ice], 'encoding-failure', encode=fail_encoding)
        self.assertEqual(self.dump(), before)
        with self.db() as db:
            cap = allowances(db, self.uid)[4]
            used = sum(i['group'] == 4 for i in load_items(db, self.uid))
            for _ in range(cap-used):
                grant_items(db, [dict(template=800000, metadata=VERIFIED_TEMPLATES[800000],
                    group=4, quantity=TEMPLATE_MAX_STACKS[800000])], self.uid)
        before = self.dump()
        with self.assertRaises(ValueError):
            self.perform([ice], 'full-reward-bag')
        self.assertEqual(self.dump(), before)

    def test_persisted_restrictions_ownership_and_phase_do_not_consume(self):
        from els_server.storage.item_locks import assign as lock
        from els_server.storage.item_expiration import assign as expire
        from els_server.storage.item_seals import assign as seal
        for name in ('locked', 'timed', 'sealed', 'equipped'):
            ice = self.grant(800018)
            with self.db() as db:
                if name == 'locked':
                    lock(db, self.uid, ice['uid'], 2200000000)
                elif name == 'timed':
                    expire(db, self.uid, ice['uid'], 2200000000)
                elif name == 'sealed':
                    seal(db, self.uid, ice['uid'], True, 0)
            if name == 'equipped':
                from els_server.domain.fashion_state import move_fashion
                move_fashion(self.path, struct.pack('>BiBiB', 27, ice['slot'], 9,
                    FASHION_EQUIP_SLOTS[800018], 0), self.uid)
            before = self.dump()
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.perform([ice], name)
            self.assertEqual(self.dump(), before)
        other = Characters(self.path, 2).create('ForeignIce', 1, 'create-other')['uid']
        unblocked = self.grant(800018)
        before = self.dump()
        with self.assertRaises(ValueError):
            decompose(self.path, other, request(unblocked['uid']), 'foreign', account_id=2)
        self.assertEqual(self.dump(), before)
        s = self.session()
        s.role = 'game'
        s.phase = 'dungeon'
        response = handle(s, Event(0x202, kind=0x1c0, payload=request(unblocked['uid'])), 102)
        self.assertEqual(struct.unpack_from('>i', response[0].payload)[0], -1)
        self.assertEqual(self.dump(), before)

    def test_registered_hanger_keeps_account_appearance_and_returns_only_45(self):
        from els_server.storage import wardrobe
        ice = self.grant(800018)
        with self.db() as db:
            wardrobe.assign(db, self.uid, dict(ice, wardrobe_hanger=True))
            db.execute('INSERT INTO wardrobe_account_sources VALUES(?,?,?,?)',
                       (1, ice['uid'], ice['template'], self.uid))
            before = wardrobe.counts(db, self.uid, 1)
        self.perform([ice])
        self.assertEqual(self.totals()[130047], 45)
        with self.db() as db:
            self.assertEqual(wardrobe.counts(db, self.uid, 1), before)
            self.assertIsNone(db.execute('SELECT 1 FROM wardrobe_item_state WHERE item_uid=?',
                                        (ice['uid'],)).fetchone())


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(IceDecomposition)
    if len(sys.argv) > 1:
        suite = unittest.TestSuite(IceDecomposition(name) for name in sys.argv[1:])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    output = dict(ok=result.wasSuccessful(), tests=result.testsRun,
                  failures=len(result.failures), errors=len(result.errors), evidence=EVIDENCE,
                  base=str(BASE), candidate=str(CANDIDATE),
                  candidate_sha256={str(p.relative_to(CANDIDATE)).replace('\\', '/'):
                      hashlib.sha256(p.read_bytes()).hexdigest() for p in CANDIDATE.rglob('*.py')},
                  remaining_test_directories=[p.name for p in WORK.glob('fixed45-owned-*')],
                  deployed=False, natural_GUI=False)
    # Keep every attempt, including harness errors; successful cases need not rerun.
    number = len(list(WORK.glob('fixed45-test-attempt-*.json')))+1
    (WORK/f'fixed45-test-attempt-{number}.json').write_text(
        json.dumps(output, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    sys.exit(0 if result.wasSuccessful() else 1)
