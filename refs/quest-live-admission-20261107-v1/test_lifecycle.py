"""Shared quest candidate on owned accounts, saved inputs and original handlers."""
from contextlib import contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
BASE=Path(json.loads((HERE/'base.json').read_bytes())['parent'])
BASELINE='--baseline' in sys.argv
if BASELINE:sys.argv.remove('--baseline')
sys.dont_write_bytecode=True
sys.path[:0]=[str(BASE),str(BASE/'vendor')]
import els_server.domain
if not BASELINE:els_server.domain.__path__.insert(0,str(HERE/'source/els_server/domain'))
spec=importlib.util.spec_from_file_location('owned_quest_fixture',HERE/'fixture.py')
f=importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)
f.EXPECT_LIVE=True
from els_server.domain import tutorial_quests,quest_flow
from els_server.protocol.protocol_codec import Event


class Repaired(f.Lifecycle):
    def observe_level(self):
        return f.encoded(quest_flow.observe(self.s,[Event(0x201,kind=0xc1,payload=b'')]))

    def deferred(self):
        self.historical_parent()
        tutorial_quests.restore_initialization(self.state)
        self.observe_level()
        self.level(2)

    def test_live_F0_no_reward_cold_read_and_idle_no_scan(self):
        self.deferred()
        before=self.actor.get_inventory_snapshot()
        with patch.object(tutorial_quests,'restore_initialization',wraps=tutorial_quests.restore_initialization) as restore:
            notices=self.observe_level()
            self.assertIn(100020,self.active())
            self.assertTrue(any(e.kind==0xf0 and struct.unpack_from('>i',e.payload)[0]==100020 for e in notices))
            self.assertFalse(any(e.kind in (0xf4,0xf5) for e in notices))
            self.assertEqual(before,self.actor.get_inventory_snapshot())
            saved=f.dump(self.path)
            self.assertEqual(self.observe_level(),[])
            self.assertEqual(f.encoded(quest_flow.observe(self.s)),[])
            self.assertEqual(restore.call_count,1)
            self.assertEqual(saved,f.dump(self.path))
        self.assertEqual(self.active(),{r['id']:r for r in f.QuestState(self.path,self.uid,account_id=self.aid).snapshot()['active']})

    def test_real_other_quest_reward_levels_up_and_resumes_mainline(self):
        self.historical_parent()
        self.town(20001)
        # Legal saved Lv1 just below Lv2; the original30140 reward earns EXP.
        f.sql(self.path,'UPDATE reward_balances SET experience=? WHERE uid=?',
              (f.client_data().thresholds[1]-1,self.uid))
        self.observe_level()
        self.assertNotIn(100020,self.active())
        reply=self.send(0xee,30140,full=True)
        self.assertEqual(next(e for e in reply if e.kind==0xef).payload,bytes(4))
        self.assertTrue(all(self.active()[30140]['objectives'].values()))
        reply=self.send(0xf4,30140,full=True)
        self.assertEqual(next(e for e in reply if e.kind==0xf5).payload[:4],bytes(4))
        self.assertGreaterEqual(self.actor.character()['level'],2)
        self.assertIn(100020,self.active())
        self.assertTrue(any(e.kind==0xf0 and struct.unpack_from('>i',e.payload)[0]==100020 for e in reply))
        self.assertEqual(self.actor.get_location()['map'],20001)
        self.assertIn(30140,self.state.completed())
        self.assertNotIn(100020,self.state.completed())

    def test_all_three_manual_abandons_stay_abandoned_after_changes(self):
        self.deferred()
        self.observe_level()
        self.send(0xfa,100020)
        self.level(3)
        self.observe_level()
        self.assertNotIn(100020,self.active())
        self.town(20002)
        self.level(8)
        self.observe_level()
        self.assertIn(100090,self.active())
        self.send(0xfa,100090)
        self.level(9)
        self.observe_level()
        self.assertNotIn(100090,self.active())
        self.town(20000)
        self.level(99)
        self.observe_level()
        self.assertIn(52700,self.active())
        self.send(0xfa,52700)
        # Existing item-change notification rechecks eligibility, not rewards.
        f.encoded(quest_flow.observe(self.s,[Event(0x201,kind=0x105,payload=b'')]))
        self.assertNotIn(52700,self.active())

    def test_unstable_scene_and_retired_actor_do_not_accept(self):
        self.deferred()
        before=f.dump(self.path)
        with patch.object(self.s,'pending_map',20001):self.observe_level()
        with patch.object(self.s,'dungeon_return_pending',True):self.observe_level()
        with patch.object(self.s,'released',True):self.observe_level()
        with patch.dict(self.app.playing,{},clear=True):self.observe_level()
        self.s.completed.remove(0x227)
        self.observe_level()
        self.s.completed.add(0x227)
        self.assertNotIn(100020,self.active())
        self.assertEqual(before,f.dump(self.path))
        self.observe_level()
        self.assertIn(100020,self.active())

    def test_writer_wait_and_precommit_actor_changes_rollback(self):
        self.deferred()
        before=f.dump(self.path)
        real=tutorial_quests.write_transaction
        @contextmanager
        def retired_after_lock(db):
            with real(db):
                with patch.dict(self.app.playing,{},clear=True):yield
        with patch.object(tutorial_quests,'write_transaction',retired_after_lock):
            with self.assertRaises(ValueError):self.observe_level()
        self.assertEqual(before,f.dump(self.path))
        encode=f.encode_event
        def retire_at_encoding(event):
            result=encode(event)
            if event.kind==0xf0:self.app.playing.pop(self.aid,None)
            return result
        try:
            with patch('els_server.protocol.protocol_codec.encode_event',side_effect=retire_at_encoding):
                with self.assertRaises(ValueError):self.observe_level()
        finally:self.app.playing[self.aid]=self.s
        self.assertEqual(before,f.dump(self.path))
        self.observe_level()
        self.assertIn(100020,self.active())

    def test_new_acceptance_encoding_failure_rolls_back_then_recovers(self):
        self.deferred()
        before=f.dump(self.path)
        encode=f.encode_event
        def fail_F0(event):
            if event.kind==0xf0:raise ValueError('owned new acceptance encoding failure')
            return encode(event)
        with patch('els_server.protocol.protocol_codec.encode_event',side_effect=fail_F0):
            with self.assertRaisesRegex(ValueError,'owned new acceptance encoding failure'):self.observe_level()
        self.assertEqual(before,f.dump(self.path))
        notices=self.observe_level()
        self.assertTrue(any(e.kind==0xf0 for e in notices))
        self.assertIn(100020,self.active())

    def test_live_notification_cannot_skip_unfinished_tutorial(self):
        # Even a selected stable town must not turn a new tutorial's saved
        # default location into a completed arrival objective.
        self.observe_level()
        self.assertEqual(self.active()[100000]['objectives'],{100000:0})
        self.assertNotIn(100000,self.state.completed())
        self.assertNotIn(100010,self.active())


if __name__=='__main__':
    suite=(unittest.TestSuite(Repaired(name) for name in sys.argv[1:]) if len(sys.argv)>1
           else unittest.defaultTestLoader.loadTestsFromTestCase(Repaired))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    f.tmp.cleanup()
    report=dict(ok=result.wasSuccessful(),tests=result.testsRun,failures=len(result.failures),
        errors=len(result.errors),baseline=BASELINE,skipped=len(result.skipped),
        failure_methods=[t._testMethodName for t,_ in result.failures],
        error_methods=[t._testMethodName for t,_ in result.errors],
        modules={m.__name__:dict(path=m.__file__,sha256=hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest())
                 for m in (quest_flow,tutorial_quests)},
        fixture_sha256=hashlib.sha256((HERE/'fixture.py').read_bytes()).hexdigest(),
        test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        private_SQL_removed=not f.PRIVATE.exists(),production_DB_used=False,network=False,
        natural_GUI=False,natural_combat=False,worker_dispatch=False,
        note='Normal registered owned actors; controlled saved qualification/history; common native LocalSession handlers; actual30140 reward earns the tested level-up.')
    (HERE/('baseline-tests.json' if BASELINE else 'tests.json')).write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
