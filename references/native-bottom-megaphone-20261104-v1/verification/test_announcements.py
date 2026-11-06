import source
from source import HERE, CHANNEL
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from els_server.domain import server_announcements as notices
from els_server.domain.local_session import LocalSession
from els_server.protocol.server_announcement_messages import announcement


def session(**values):
    data = dict(client_build='dx11_260923', role='game', released=False,
                phase='town_ready', dungeon_substage_synced=True,
                shop_session_id='owned-session', account=SimpleNamespace(uid=1001),
                shop_test=False, enter_dungeon=True, _realtime_clock=True)
    data.update(values)
    return SimpleNamespace(**data)


class Tests(unittest.TestCase):
    def setUp(self):
        self.events = (announcement('系统公告', '第一条公告'), announcement('系统公告', '第二条公告'))
        self.policy = patch.object(notices, 'policy', return_value=(300, self.events))
        self.policy.start()
        self.addCleanup(self.policy.stop)
        self.clock = patch.object(notices.time, 'monotonic', return_value=1000.)
        self.now = self.clock.start()
        self.addCleanup(self.clock.stop)

    def test_login_interval_rotation_and_no_catchup_flood(self):
        s = session()
        self.assertEqual(notices.periodic(s), [self.events[0]])
        self.assertEqual(notices.periodic(s), [])
        self.now.return_value = 1299.999
        self.assertEqual(notices.periodic(s), [])
        self.now.return_value = 1300.
        self.assertEqual(notices.periodic(s), [self.events[1]])
        self.now.return_value = 9999.
        self.assertEqual(notices.periodic(s), [self.events[0]])
        self.assertEqual(notices.periodic(s), [])

    def test_loading_does_not_consume_first_message(self):
        s = session(phase='map_loading')
        self.assertEqual(notices.periodic(s), [])
        self.assertFalse(hasattr(s, '_server_announcement'))
        s.phase = 'town_ready'
        self.assertEqual(notices.periodic(s), [self.events[0]])

    def test_dungeon_scene_loading_and_return_keep_deadline(self):
        s = session()
        notices.periodic(s)
        s.phase = 'dungeon_loading'
        self.now.return_value = 1500.
        self.assertEqual(notices.periodic(s), [])
        s.phase = 'dungeon_active'; s.dungeon_substage_synced = False
        self.assertEqual(notices.periodic(s), [])
        s.dungeon_substage_synced = True
        self.assertEqual(notices.periodic(s), [self.events[1]])
        s.phase = 'town_ready'
        self.assertEqual(notices.periodic(s), [])

    def test_character_switch_reconnect_and_recipient_isolation(self):
        alice, bob = session(), session()
        self.assertEqual(notices.periodic(alice), [self.events[0]])
        self.assertEqual(notices.periodic(bob), [self.events[0]])
        alice.account.uid = 1002
        self.assertEqual(notices.periodic(alice), [self.events[0]])
        alice.shop_session_id = 'reconnected'
        self.assertEqual(notices.periodic(alice), [self.events[0]])
        self.assertEqual(notices.periodic(bob), [])

    def test_wrong_role_build_phase_and_released_do_not_send(self):
        for values in (dict(role='login'), dict(client_build='unknown'),
                       dict(phase='channels_ready'), dict(released=True)):
            with self.subTest(values=values):
                s = session(**values)
                self.assertEqual(notices.periodic(s), [])
                self.assertFalse(hasattr(s, '_server_announcement'))

    def test_empty_policy_disables_sending(self):
        with patch.object(notices, 'policy', return_value=(300, ())):
            s = session()
            self.assertEqual(notices.periodic(s), [])
            self.assertFalse(hasattr(s, '_server_announcement'))

    def test_actual_shared_periodic_keeps_existing_messages(self):
        existing = announcement('系统公告', '原有通知保留')
        with patch('els_server.domain.black_market_flow.periodic', return_value=[existing]), \
             patch('els_server.domain.mailbox_extras.periodic', return_value=[]), \
             patch('els_server.domain.luciel_state.periodic', return_value=[]):
            for phase in ('town_ready', 'dungeon_active'):
                s = session(phase=phase)
                result = LocalSession._periodic_notifications(s)
                self.assertEqual(result[:2], [existing, self.events[0]])
                self.assertEqual(LocalSession._periodic_notifications(s)[0], existing)


class Configuration(unittest.TestCase):
    def tearDown(self):
        notices.policy.cache_clear()

    def test_default_policy_and_invalid_text(self):
        notices.policy.cache_clear()
        interval, events = notices.policy()
        self.assertEqual(interval, 300)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].kind, 0x244)
        for text in ('', ' ', 'bad\nline', 'bad\x00line', '😀'*101):
            with self.subTest(text=text), self.assertRaises(ValueError):
                notices._text(text, 200)
        self.assertEqual(notices._text('😀'*100, 200), '😀'*100)

    def test_policy_rejects_wrong_shape_and_accepts_disabled(self):
        for data in ({}, dict(sender='系统公告', interval_seconds=True, messages=['公告']),
                     dict(sender='系统公告', interval_seconds=0, messages=['公告']),
                     dict(sender='系统公告', interval_seconds=300, messages='公告')):
            notices.policy.cache_clear()
            with patch.object(notices.Path, 'read_bytes', return_value=json.dumps(data).encode()), self.assertRaises(ValueError):
                notices.policy()
        notices.policy.cache_clear()
        data = dict(sender='系统公告', interval_seconds=300, messages=[])
        with patch.object(notices.Path, 'read_bytes', return_value=json.dumps(data).encode()):
            self.assertEqual(notices.policy(), (300, ()))


if __name__ == '__main__':
    suite = unittest.TestSuite((unittest.defaultTestLoader.loadTestsFromTestCase(Tests),
                               unittest.defaultTestLoader.loadTestsFromTestCase(Configuration)))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    proof = dict(channel=CHANNEL, tests_run=result.testsRun, passed=result.wasSuccessful(),
                 failures=len(result.failures), errors=len(result.errors),
                 natural_GUI=False, installed=False)
    (HERE / ('tests-'+CHANNEL+'.json')).write_text(json.dumps(proof, indent=2)+'\n', encoding='utf8')
    raise SystemExit(not result.wasSuccessful())
