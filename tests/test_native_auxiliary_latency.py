"""The observed auxiliary burst must not rebuild ordinary business projections."""
from types import SimpleNamespace
import unittest
from els_server.application import FriendsSession
from els_server.domain.local_session import SessionOrderError
from els_server.protocol.protocol_codec import Event


class OrdinaryRouteReached(Exception):
    pass


class AuxiliaryLatencyTests(unittest.TestCase):
    def session(self):
        session = FriendsSession.__new__(FriendsSession)
        self.enabled = True
        self.ordinary_calls = 0
        self.pending = [Event(0x201, kind=0x85, payload=b'pending')]

        def ordinary(*unused):
            self.ordinary_calls += 1
            raise OrdinaryRouteReached()

        def drain():
            messages, self.pending = self.pending, []
            return messages

        session.released = False
        session.social_overflow = False
        session.coop_error = None
        session.client_build = 'dx11_260923'
        session.role = 'game'
        session.phase = 'town_ready'
        session.identity = {'id': 2}
        session.account = SimpleNamespace(uid=1001, store=SimpleNamespace(uid=1001))
        session.mailbox = SimpleNamespace(drain=drain)
        session.application = SimpleNamespace(
            registry=SimpleNamespace(enabled=lambda identity: self.enabled),
            playing={2: session},
            world=SimpleNamespace(field_bosses=SimpleNamespace(request=ordinary)))
        return session

    def notification(self, **changes):
        values = dict(event_id=0x202, kind=0x7d0, payload=bytes(9), performers=(0,))
        values.update(changes)
        return Event(**values)

    def test_observed_burst_delivers_pending_mail_without_entering_business(self):
        session = self.session()
        expected = list(self.pending)
        self.assertEqual(session.handle(self.notification(), 1), expected)
        for sequence in range(2, 514):
            self.assertEqual(session.handle(self.notification(), sequence), [])
        self.assertEqual(self.ordinary_calls, 0)
        session.phase = 'dungeon_active'
        self.assertEqual(session.handle(self.notification(), 514), [])

    def test_disabled_and_released_connections_never_get_fast_path(self):
        session = self.session()
        self.enabled = False
        with self.assertRaises(SessionOrderError):
            session.handle(self.notification(), 1)
        self.enabled = True
        session.released = True
        with self.assertRaises(SessionOrderError):
            session.handle(self.notification(), 2)
        self.assertEqual(len(self.pending), 1)

    def test_other_requests_and_envelopes_retain_ordinary_admission(self):
        session = self.session()
        for changes in ({'kind': 0x113}, {'payload': bytes(8)}, {'payload': bytes(10)},
                        {'event_id': 0x201}, {'performers': ()}, {'uid': 1001},
                        {'target_uid': 1001}, {'payload_mode': 1}):
            with self.subTest(changes=changes), self.assertRaises(OrdinaryRouteReached):
                session.handle(self.notification(**changes), 1)
        self.assertEqual(len(self.pending), 1)

    def test_old_actor_other_build_and_loading_still_enter_ordinary_guards(self):
        for field, value in (('client_build', 'other'), ('phase', 'map_loading'),
                             ('role', 'frontend')):
            session = self.session()
            setattr(session, field, value)
            with self.subTest(field=field), self.assertRaises(OrdinaryRouteReached):
                session.handle(self.notification(), 1)
        session = self.session()
        session.application.playing[2] = object()
        with self.assertRaises(OrdinaryRouteReached):
            session.handle(self.notification(), 1)
        session = self.session()
        session.account.store.uid = 1002
        with self.assertRaises(OrdinaryRouteReached):
            session.handle(self.notification(), 1)


if __name__ == '__main__':
    unittest.main()
