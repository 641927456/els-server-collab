"""Review installed task lifecycle using only disposable owned SQL fixtures."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import unquote, urlparse

EXPECT_LIVE='--expect-live' in sys.argv
if EXPECT_LIVE:sys.argv.remove('--expect-live')

ROOT = Path('G:/els')
OUT = Path(__file__).resolve().parent
BASE = Path('G:\\els\\releases\\online\\native-server-latency-20261106-v7')
LOCAL = ROOT/'releases/local/unified-server-b6b15dc03dd7354d-f19e6906df62'
sys.dont_write_bytecode = True
sys.path[:0] = [str(BASE), str(BASE/'vendor')]
tmp = tempfile.TemporaryDirectory(prefix='owned-review-', dir=OUT)
PRIVATE = Path(tmp.name).resolve()
opened = set()


def audit(event, args):
    if event == 'sqlite3.connect':
        raw = str(args[0])
        name = unquote(urlparse(raw).path).lstrip('/') if raw.startswith('file:') else raw
        path = Path(name).resolve()
        if path == (BASE/'els_server/data/client/catalog.sqlite3').resolve():
            assert 'mode=ro' in raw and 'immutable=1' in raw
        else:
            assert path.is_relative_to(PRIVATE), ('Non-fixture SQL', str(path))
        opened.add(str(path))
    if event.startswith('socket.') or event in ('subprocess.Popen', 'os.system'):
        raise PermissionError('Offline task review only')


sys.addaudithook(audit)
from els_server.domain.local_session import LocalAccount, LocalSession
from els_server.storage.local_state import LocalState
from els_server.storage.characters import Characters
from els_server.storage.game_schema import prepare
from els_server.storage.seal_quests import QuestState
from els_server.domain.seal_quests import quest_catalog, sequence, target
from els_server.domain.tutorial_quests import restore_initialization
from els_server.domain import quest_flow
from els_server.protocol.protocol_codec import Event, encode_event
from els_server.game_data import client_data
from els_server.storage.epic_followups import _arrival_roots
from els_server.application import Application, FriendsSession
from els_server.config import ServerConfig
from els_server.storage.accounts import Accounts

checks = []


def sql(path, query, args=()):
    with closing(sqlite3.connect(path)) as db, db:
        return db.execute(query, args).fetchall()


def dump(path):
    with closing(sqlite3.connect(path)) as db:
        return tuple(db.iterdump())


def encoded(events):
    for event in events:
        encode_event(event)
    return events


class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.path = PRIVATE/(self._testMethodName+'.sqlite3')
        prepare(self.path)
        self.app=Application(ServerConfig(state_file=self.path,
            accounts_file=PRIVATE/(self._testMethodName+'-accounts.sqlite3'),
            log_dir=PRIVATE/'logs'))
        self.addCleanup(self.close_app)
        self.app.registry=Accounts(self.app.config.accounts_file)
        identity=self.app.registry.create('reviewqa')
        self.aid=identity['id']
        roster = Characters(self.path, self.aid)
        char = roster.create('Review', 1, self._testMethodName)
        self.uid = char['uid']
        root = LocalAccount(LocalState(self.path, self.uid),self.aid,'reviewqa')
        root.enable_characters(characters=roster)
        self.actor = root.for_character(self.uid)
        self.state = QuestState(self.path, self.uid, account_id=self.aid)
        self.state.snapshot()
        self.s = FriendsSession(self.app,identity,self.actor, enter_town=True, enter_dungeon=True,
                              client_build='dx11_260923', npc_slot_test=True,
                              gate_test=True, population_test=True,
                              clear_test=True, reward_test=True, item_test=True)
        self.s.role = 'game'
        self.s.phase = 'town_ready'
        self.s.active_map = self.s.pending_map = 20000
        self.s.completed.update((0x28,0x225, 0x227))
        self.app.accounts[self.aid]=root
        self.app.playing[self.aid]=self.s
        self.seq = 10

    def close_app(self):
        # This fixture deliberately dispatches synchronously on this thread.
        # Close its registry's enabled-reader on the same creating thread.
        registry=self.app.registry
        if registry is not None:
            registry.close()
            self.app.registry=None
        self.app.close()

    def level(self, n):
        sql(self.path, 'UPDATE characters SET level=? WHERE uid=?', (n, self.uid))
        sql(self.path, 'UPDATE reward_balances SET experience=? WHERE uid=?',
            (0 if n == 1 else client_data().thresholds[n-1], self.uid))

    def town(self, town):
        self.actor.save_location(town, 0, 0, (0., 0., 0.))
        self.s.active_map = self.s.pending_map = town

    def historical_parent(self):
        # Explicit delayed-history fixture, not a fabricated earned reward.
        sql(self.path, 'INSERT INTO completed_quests VALUES (?,?,?,?)',
            (self.uid, 100010, 1, '{"fixture":true}'))

    def active(self):
        return {r['id']:r for r in self.state.snapshot()['active']}

    def send(self, kind, qid, npc=None, *, full=False):
        self.seq += 1
        if npc is None:npc=quest_catalog().quest(qid)['m_eStartNPCID'] if kind==0xee else 0
        body = (struct.pack('>ii', qid, npc) if kind == 0xee else
                struct.pack('>i', qid) if kind == 0xfa else
                struct.pack('>iiI5B', qid, npc, 0, 0, 0, 1, 1, 0))
        event = Event(0x202, performers=(0,), kind=kind, payload=body)
        if full:
            return encoded(LocalSession.handle(self.s,event,self.seq))
        replies = quest_flow.handle(self.s, event, self.seq)
        return encoded(replies+quest_flow.observe(self.s, replies))

    def scene_ready(self, town):
        # Controlled initial/return load admission; original227 handler saves
        # location and supplies228. This is not a paid-warp or GUI simulation.
        self.s.pending_map = town
        self.s.phase = 'square_accepted'
        self.seq += 1
        return encoded(LocalSession.handle(self.s,Event(0x202, performers=(0,), kind=0x227,
            payload=struct.pack('>fffBH', 0., 0., 0., 0, 0)), self.seq))

    def test_same_town_reward_accepts_next_and_is_atomic(self):
        restore_initialization(self.state, defer_starter_arrival=True)
        before = dump(self.path)
        reply = self.send(0xf4, 100000)
        self.assertEqual(struct.unpack_from('>i', reply[0].payload)[0], 187)
        self.assertEqual(before, dump(self.path))
        encoded(self.state.record('controlled-town', dict(kind='visit_town', town=20000,
            dungeon=0, level=1), b'controlled arrival after tutorial'))
        reply = self.send(0xf4, 100000, full=True)
        self.assertEqual(struct.unpack_from('>i', next(e for e in reply if e.kind==0xf5).payload)[0], 0)
        self.assertIn(100010, self.active())
        self.assertTrue(any(e.kind==0xf0 and struct.unpack_from('>i',e.payload)[0]==100010 for e in reply))
        self.assertEqual(self.actor.get_location()['map'], 20000)
        before = dump(self.path)
        # New request identity, already-completed reward: no new grant.
        self.send(0xf4, 100000)
        after = dump(self.path)
        # Only the idempotent action receipt for this new sequence may differ.
        self.assertEqual([x for x in before if not x.startswith('INSERT INTO "quest_actions"')],
                         [x for x in after if not x.startswith('INSERT INTO "quest_actions"')])
        encoded(self.state.record('controlled-tree-clear', dict(kind='clear', dungeon=30000,
            level=1, rank=None), b'controlled clear'))
        before = dump(self.path)
        with patch('els_server.protocol.quest_messages.reward_ack', side_effect=ValueError('owned encoder failure')):
            with self.assertRaisesRegex(ValueError,'owned encoder failure'):
                quest_flow.handle(self.s, Event(0x202, performers=(0,), kind=0xf4,
                    payload=struct.pack('>iiI5B',100010,0,0,0,0,1,1,0)), 999)
        self.assertEqual(before, dump(self.path))
        checks.append(dict(case=self._testMethodName, same_town_live_F0=True,
            incomplete_rejected=True, repeated_reward_no_increment=True,
            encode_failure_rollback=True, full_LocalSession_claim=True))

    def test_deferred_level_idle_vs_arrival(self):
        self.historical_parent()
        restore_initialization(self.state)
        self.assertNotIn(100020, self.active())
        encoded(quest_flow.observe(self.s))
        self.level(2)  # A controlled change in qualification, not natural EXP.
        before = dump(self.path)
        notices = encoded(quest_flow.observe(self.s, [Event(0x201,kind=0xc1,payload=b'')]))
        notices += encoded(quest_flow.observe(self.s))
        (self.assertIn if EXPECT_LIVE else self.assertNotIn)(100020,self.active())
        if EXPECT_LIVE:return
        if not EXPECT_LIVE:self.assertEqual(before,dump(self.path))
        no_move_notices = [e.kind for e in notices]
        ready = self.scene_ready(20000)
        self.assertIn(100020, self.active())
        self.assertTrue(any(e.kind==0xf0 for e in ready))
        checks.append(dict(case=self._testMethodName, underlevel_not_accepted=True,
            qualified_same_town_tick_did_NOT_accept=True, no_move_kinds=no_move_notices,
            same_town_scene_reload_accepts=True, full_LocalSession_227=True))

    def test_manual_accept_in_place_and_refusals(self):
        self.historical_parent()
        before = dump(self.path)
        reply = self.send(0xee, 100020)
        self.assertNotEqual(struct.unpack_from('>i',reply[0].payload)[0],0)
        self.assertEqual(before, dump(self.path))
        self.level(2)
        reply = self.send(0xee,100020,full=True)
        self.assertEqual(struct.unpack_from('>i',next(e for e in reply if e.kind==0xef).payload)[0],0)
        self.assertIn(100020,self.active())
        self.assertEqual(self.actor.get_location()['map'],20000)
        self.send(0xfa,100020)
        self.scene_ready(20000)
        self.assertNotIn(100020,self.active())
        self.level(99)
        before = dump(self.path)
        reply = self.send(0xee,100030,10005)
        self.assertNotEqual(struct.unpack_from('>i',reply[0].payload)[0],0)
        self.assertEqual([x for x in before if not x.startswith('INSERT INTO "location"')],
                         [x for x in dump(self.path) if not x.startswith('INSERT INTO "location"')])
        checks.append(dict(case=self._testMethodName, manual_same_town_works=True,
            full_LocalSession_EE=True, underlevel_rejected=True,
            wrong_town_rejected=True, manual_abandon_preserved_on_arrival=True))

    def test_regional_arrival_and_remote_claim(self):
        self.level(99)
        # A saved unfinished Ruben story does not suppress a new town root.
        self.state.action('accept',dict(quest=100000,npc=10025),'owned-old-root',lambda r:[])
        before = self.actor.get_inventory_snapshot()
        reply = self.scene_ready(20001)
        self.assertEqual(self.active()[100030]['objectives'],{100030:1})
        self.assertIn(100000,self.active())
        self.assertNotIn(100030,self.state.completed())
        self.assertEqual(before,self.actor.get_inventory_snapshot())
        self.assertTrue(any(e.kind==0xf0 for e in reply))
        before = dump(self.path)
        self.scene_ready(20001)
        self.assertEqual(before,dump(self.path))
        self.town(20000)
        before = dump(self.path)
        reply = self.send(0xf4,100030,10005)
        self.assertNotEqual(struct.unpack_from('>i',reply[0].payload)[0],0)
        self.assertEqual(before,dump(self.path))
        reply = self.send(0xf4,100030,0,full=True)
        self.assertEqual(struct.unpack_from('>i',next(e for e in reply if e.kind==0xf5).payload)[0],0)
        self.assertIn(100030,self.state.completed())
        cold = QuestState(self.path,self.uid,account_id=self.aid)
        self.assertEqual(cold.snapshot(),self.state.snapshot())
        checks.append(dict(case=self._testMethodName, region_root_at_destination=True,
            arrival_no_reward=True, prior_story_retained=True, arrival_repeat_no_increment=True,
            remote_window_claim_works=True, wrong_NPC_context_rejected=True, cold_read=True))

    def test_region_root_qualification_without_moving(self):
        self.town(20002)
        self.level(7)
        self.assertFalse(restore_initialization(self.state,live=True)[1])
        self.assertNotIn(100090,self.active())
        encoded(quest_flow.observe(self.s))
        self.level(8)
        encoded(quest_flow.observe(self.s,[Event(0x201,kind=0xc1,payload=b'')]))
        encoded(quest_flow.observe(self.s))
        (self.assertIn if EXPECT_LIVE else self.assertNotIn)(100090,self.active())
        if EXPECT_LIVE:return
        # A fresh character-selection initialization in the SAME saved town
        # restores the now-qualified regional root, no inter-town travel.
        self.s.phase='characters_ready'
        encoded([quest_flow.initialization(self.s)])
        self.s.phase='town_ready'
        self.assertIn(100090,self.active())
        checks.append(dict(case=self._testMethodName, level7_not_accepted=True,
            level8_same_town_tick_did_NOT_accept=True, same_town_cold_login_accepts=True))

    def test_collection99_root_same_trigger_variant(self):
        self.level(98)
        self.scene_ready(20000)
        self.assertNotIn(52700,self.active())
        self.level(99)
        encoded(quest_flow.observe(self.s,[Event(0x201,kind=0xc1,payload=b'')]))
        encoded(quest_flow.observe(self.s))
        (self.assertIn if EXPECT_LIVE else self.assertNotIn)(52700,self.active())
        if EXPECT_LIVE:return
        before=self.actor.get_inventory_snapshot()
        notices=self.scene_ready(20000)
        self.assertIn(52700,self.active())
        self.assertTrue(any(e.kind==0xf0 and struct.unpack_from('>i',e.payload)[0]==52700 for e in notices))
        self.assertEqual(before,self.actor.get_inventory_snapshot())
        checks.append(dict(case=self._testMethodName, level98_not_accepted=True,
            level99_same_town_tick_did_NOT_accept=True, scene_reload_accepts_collection52700=True,
            auto_accept_does_not_reward=True))


if __name__=='__main__':
    paths = ['els_server/domain/quest_flow.py','els_server/domain/tutorial_quests.py',
             'els_server/storage/epic_followups.py','els_server/storage/seal_quests.py',
             'els_server/domain/seal_quests.py','els_server/protocol/quest_messages.py']
    binding=[]
    for name in paths:
        online=hashlib.sha256((BASE/name).read_bytes()).hexdigest()
        local=hashlib.sha256((LOCAL/name).read_bytes()).hexdigest()
        binding.append(dict(path=name,online_sha256=online,local_sha256=local,same=online==local))
    if len(sys.argv)>1:
        suite=unittest.TestSuite(Lifecycle(name) for name in sys.argv[1:])
        previous=json.loads((OUT/'result.json').read_bytes())
        if not EXPECT_LIVE:checks.extend(row for row in previous['checks'] if row['case'] not in sys.argv[1:])
    else:suite=unittest.defaultTestLoader.loadTestsFromTestCase(Lifecycle)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    catalog=quest_catalog()
    main={i:q for i,q in catalog.quests.items() if q['m_eQuestType']==5}
    static=dict(registered_all=len(catalog.quests),registered_main=len(main),
        undefined_after=[dict(parent=i,child=j) for i,q in main.items()
            for j in sequence(q.get('m_iAfterQuestID',{})) if j and j not in catalog.quests],
        missing_predecessors=[dict(quest=i,parent=j) for i,q in main.items()
            for j in sequence(q['QuestCondition']['m_vecBeforeQuestID']) if j and j not in catalog.quests],
        arrival_definitions=[dict(quest=i,town=town,level=catalog.quest(i)['QuestCondition']['m_iLevel'])
            for town,ids in _arrival_roots().items() for i in ids])
    report=dict(ok=result.wasSuccessful(),tests_executed_this_run=result.testsRun,
        total_successful_cases=len(checks),failures=len(result.failures),
        expects_automatic_acceptance_without_scene_reload=EXPECT_LIVE,
        errors=len(result.errors),checks=checks,online_snapshot=str(BASE),local_snapshot=str(LOCAL),
        binding=binding,arrival_roots=_arrival_roots(),static=static,
        caveat='Controlled SQL qualification/history and scene-load fixtures; no natural GUI/combat or remote host SHA collection.',
        production_DB_used=False,network=False,process_started=False,
        fixture_corrections='Use registered FriendsSession actor; real configured start NPC; encoder fault is expected to escape after rollback. Prior passed case retained unchanged.')
    tmp.cleanup()
    report['private_SQL_removed']=not PRIVATE.exists()
    (OUT/('live-regression-result.json' if EXPECT_LIVE else 'result.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
