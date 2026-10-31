"""Owned private fixtures for root lifetime, recovery pins and failed teardown."""
import asyncio
import gc
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import weakref

TASK = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ['ELS_RUNTIME_ROOT']).resolve()
if RUNTIME not in ((TASK/'runtimes/online').resolve(), (TASK/'runtimes/local').resolve()):
    raise RuntimeError('Only owned runtimes are allowed')
sys.path.insert(0, str(RUNTIME))
from els_server.application import Application, FriendsSession
from els_server.account_cache import AccountCache
from els_server.accounts_gateway import AccountGateway
from els_server.cleanup import cleanup_all
from els_server.domain.friends_world import FriendsWorld
from els_server.domain import guild_agit_flow
from els_server.domain.field_boss import FieldBosses
from els_server.storage import tutorial_recovery as recovery


def leaves(error):
    if isinstance(error, BaseExceptionGroup):
        return [leaf for child in error.exceptions for leaf in leaves(child)]
    return [error]


class Actor:
    def __init__(self, uid=1001):
        self.account = SimpleNamespace(uid=uid)
        self.phase = 'town_ready'
        self.released = False
        self.guild_agit = None


class Root:
    def __init__(self):
        self.root = self
        self.character_accounts = {1001: self}
        self.uid = 1001
        self.account_id = 2


class TeardownTests(unittest.TestCase):
    def test_cache_snapshot_during_worker_insertions_and_gc(self):
        cache, finished, failures = AccountCache(), threading.Event(), []
        def work():
            try:
                for index in range(1000):
                    cache[index] = Root()
                    if index % 100 == 0:
                        gc.collect()
            except BaseException as error:
                failures.append(error)
            finally:
                finished.set()
        worker = threading.Thread(target=work)
        worker.start()
        try:
            while not finished.is_set():
                observed = cache.snapshot()
                self.assertEqual(observed['roots'], observed['roles'])
        finally:
            worker.join(4)
        self.assertFalse(worker.is_alive())
        self.assertEqual(failures, [])
        gc.collect()
        observed = cache.snapshot()
        self.assertEqual((observed['roots_created'], observed['roots_reclaimed']), (1000, 1000))
        self.assertEqual(observed['roots'], 0)

    def test_cleanup_attempts_every_stage_and_preserves_original_errors(self):
        first, second = ValueError('first'), RuntimeError('second')
        called = []
        def fail(error):
            called.append(error)
            raise error
        with self.assertRaises(ValueError) as single:
            cleanup_all(lambda: fail(first), lambda: called.append('after'))
        self.assertIs(single.exception, first)
        with self.assertRaises(BaseExceptionGroup) as multiple:
            cleanup_all(lambda: fail(first), lambda: fail(second), lambda: called.append('last'))
        self.assertEqual(leaves(multiple.exception), [first, second])
        self.assertEqual(called[-1], 'last')

    def test_guild_notice_failure_revokes_context_and_attempts_other_peer(self):
        actor, bad, good = Actor(), Actor(1002), Actor(1003)
        for peer in (actor, bad, good):
            peer.phase = 'guild_agit_ready'
            peer.guild_agit = dict(values=(peer.account.uid,), guild=7)
        error = ValueError('owned guild notice fault')
        sent = []
        def send(peer, notice):
            sent.append(peer)
            if peer is bad:
                raise error
        actor.application = SimpleNamespace(playing={1: actor, 2: bad, 3: good}, world=SimpleNamespace(send=send))
        with self.assertRaises(ValueError) as caught:
            guild_agit_flow.disconnect(actor)
        self.assertIs(caught.exception, error)
        self.assertIsNone(actor.guild_agit)
        self.assertEqual(sent, [bad, good])
        guild_agit_flow.disconnect(actor)
        self.assertEqual(sent, [bad, good])

    def test_world_notice_failure_still_removes_town_party_and_invitations(self):
        world = FriendsWorld()
        actor, other = Actor(), Actor(1002)
        party = dict(id=9, members=[actor, other], ready={actor, other}, leader=actor)
        world.parties[9] = party
        world.party_of = {actor: party, other: party}
        world.members[actor] = world.members[other] = 'town'
        world.towns['town'] = {actor: object(), other: object()}
        world.invitations[other] = dict(inviter=actor)
        error = ValueError('owned world notice fault')
        def send(*args, **kwargs):
            raise error
        with patch.object(world, 'send', send), self.assertRaises(BaseExceptionGroup) as caught:
            world.disconnect(actor)
        self.assertTrue(all(item is error for item in leaves(caught.exception)))
        self.assertNotIn(actor, world.members)
        self.assertNotIn(actor, world.towns['town'])
        self.assertNotIn(actor, world.party_of)
        self.assertNotIn(other, world.party_of)
        self.assertNotIn(9, world.parties)
        self.assertEqual(world.invitations, {})
        self.assertEqual(party['members'], [other])
        self.assertEqual(party['ready'], set())

    def test_empty_town_removed_even_if_encoder_fails(self):
        world, actor = FriendsWorld(), Actor()
        world.members[actor] = 'last'
        world.towns['last'] = {actor: object()}
        with patch('els_server.domain.friends_world.wire.town_members', side_effect=ValueError('codec')):
            with self.assertRaises(ValueError):
                world.leave(actor)
        self.assertEqual(world.members, {})
        self.assertEqual(world.towns, {})

    def test_field_disconnect_finishes_state_after_notice_failure(self):
        actor, other = Actor(), Actor(1002)
        party = dict(ready={actor, other})
        error = ValueError('owned field notice fault')
        def send(*args):
            raise error
        world = SimpleNamespace(send=send, party_of={actor: party})
        field = FieldBosses(world)
        room = SimpleNamespace(phase='active', members=(actor, other))
        field.rooms = {actor: room, other: room}
        with self.assertRaises(ValueError) as caught:
            field.detach(actor)
        self.assertIs(caught.exception, error)
        self.assertNotIn(actor, field.rooms)
        self.assertEqual(room.phase, 'failed')
        self.assertEqual(other.field_result, 'member disconnected')
        self.assertEqual(party['ready'], set())


class LifetimeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        scratch = TASK/'scratch/session-lifetime'
        scratch.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix=RUNTIME.name+'-', dir=scratch)
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name)/'owned.sqlite3'
        config = SimpleNamespace(mode='friends', profile='integrated_dx11', state_file=self.path,
                                 session_options=lambda: {})
        self.app = Application(config)
        self.addCleanup(self.app.close)

    async def until(self, predicate):
        async with asyncio.timeout(4):
            while not predicate():
                await asyncio.sleep(.002)

    async def test_frontend_handoff_and_selected_roles_keep_root_until_last_reference(self):
        identity = dict(id=2, name='synthetic')
        first = await self.app.session(identity=identity)
        root = first.account
        second = await self.app.session(identity=identity)
        self.assertIs(second.account, root)
        reference = weakref.ref(root)
        await self.app.release(first)
        del first, root
        gc.collect()
        self.assertIs(second.account, reference())
        self.assertIs(self.app.accounts[2], second.account)
        await self.app.release(second)
        del second
        await self.app.call(lambda: None)
        gc.collect()
        self.assertIsNone(reference())
        self.assertNotIn(2, self.app.accounts)
        state = self.app.accounts.snapshot()
        self.assertEqual((state['roots'], state['roots_created'], state['roots_reclaimed']), (0, 1, 1))
        rebuilt = await self.app.session(identity=identity)
        self.assertEqual(rebuilt.account.account_id, 2)
        self.assertIsNone(rebuilt.account.uid)
        self.assertEqual(rebuilt.account.characters.list(), [])
        self.assertEqual(self.app.accounts.snapshot()['roots_created'], 2)

    async def test_cached_role_group_is_collected_without_evicting_live_actor(self):
        session = await self.app.session(identity=dict(id=1, name='synthetic'))
        root = session.account
        reference, role_reference = weakref.ref(root), weakref.ref(root.character_accounts[1001])
        self.assertEqual(self.app.accounts.snapshot()['roles'], 1)
        gc.collect()
        self.assertIs(self.app.accounts[1], root)
        saved = root.character_identity()
        await self.app.release(session)
        del session, root
        await self.app.call(lambda: None)
        gc.collect()
        self.assertIsNone(reference())
        self.assertIsNone(role_reference())
        cold = await self.app.session(identity=dict(id=1, name='synthetic'))
        self.assertEqual(cold.account.character_identity(), saved)

    async def test_native_terms_survive_gapped_channel_handoff_but_not_other_account_or_application(self):
        from els_server.domain.local_session import SessionOrderError
        from els_server.protocol.protocol_codec import Event
        self.app.registry = SimpleNamespace(enabled=lambda account_id: True)
        self.app.config.session_options = lambda: dict(enter_town=True, client_build='dx11_260923')
        first = await self.app.session(identity=dict(id=2, name='synthetic'))
        first.phase = 'session_ready'
        await self.app.call(first.handle, Event(0x202, kind=0x39))
        self.assertTrue(first.account.has_terms())
        reference = weakref.ref(first.account)
        await self.app.release(first)
        del first
        await self.app.call(lambda: None)
        gc.collect()
        self.assertIsNone(reference())
        self.assertNotIn(2, self.app.accounts)
        fresh = await self.app.session(identity=dict(id=2, name='synthetic'))
        fresh.phase = 'session_ready'
        await self.app.call(fresh.handle, Event(0x202, kind=0x485))
        self.assertEqual(fresh.phase, 'characters_ready')
        other = await self.app.session(identity=dict(id=3, name='synthetic-other'))
        other.phase = 'session_ready'
        self.assertFalse(other.account.has_terms())
        with self.assertRaises(SessionOrderError):
            await self.app.call(other.handle, Event(0x202, kind=0x485))
        restarted = Application(self.app.config)
        self.addCleanup(restarted.close)
        restarted.registry = self.app.registry
        new = await restarted.session(identity=dict(id=2, name='synthetic'))
        new.phase = 'session_ready'
        self.assertFalse(new.account.has_terms())
        with self.assertRaises(SessionOrderError):
            await restarted.call(new.handle, Event(0x202, kind=0x485))

    async def test_terms_holder_does_not_require_a_release_callback(self):
        session = await self.app.session(identity=dict(id=2, name='synthetic'))
        session.account.accept_terms()
        reference = weakref.ref(session.account)
        del session
        await self.app.call(lambda: None)
        gc.collect()
        self.assertIsNone(reference())
        rebuilt = await self.app.session(identity=dict(id=2, name='synthetic'))
        self.assertTrue(rebuilt.account.has_terms())

    async def test_queued_and_cancelled_started_worker_own_root_until_actual_retirement(self):
        root = Root()
        self.app.accounts[2] = root
        reference = weakref.ref(root)
        gate, entered = threading.Event(), threading.Event()
        self.addCleanup(gate.set)
        def blocked():
            entered.set()
            gate.wait(3)
        blocker = asyncio.create_task(self.app.call(blocked))
        await asyncio.to_thread(entered.wait, 2)
        job_entered, job_gate = threading.Event(), threading.Event()
        self.addCleanup(job_gate.set)
        def owned_work(held):
            self.assertIs(self.app.accounts[2], held)
            job_entered.set()
            job_gate.wait(3)
            return held.account_id
        work = asyncio.create_task(self.app.call(owned_work, root))
        await self.until(lambda: self.app.business_queue.inflight == 2)
        del root
        gc.collect()
        self.assertIsNotNone(reference())
        gate.set()
        await blocker
        await asyncio.to_thread(job_entered.wait, 2)
        work.cancel()
        await asyncio.gather(work, return_exceptions=True)
        gc.collect()
        self.assertIsNotNone(reference())
        job_gate.set()
        await self.app.call(lambda: None)
        del work
        gc.collect()
        self.assertIsNone(reference())

    async def test_cancelled_queued_work_keeps_its_reference_until_dequeue(self):
        root = Root()
        self.app.accounts[2] = root
        reference = weakref.ref(root)
        gate, entered = threading.Event(), threading.Event()
        self.addCleanup(gate.set)
        def blocked():
            entered.set()
            gate.wait(3)
        blocker = asyncio.create_task(self.app.call(blocked))
        await asyncio.to_thread(entered.wait, 2)
        invoked = []
        work = asyncio.create_task(self.app.call(lambda held: invoked.append(held), root))
        await self.until(lambda: self.app.business_queue.inflight == 2)
        work.cancel()
        await asyncio.gather(work, return_exceptions=True)
        del root, work
        gc.collect()
        self.assertIsNotNone(reference())
        gate.set()
        await blocker
        await self.app.call(lambda: None)
        gc.collect()
        self.assertEqual(invoked, [])
        self.assertIsNone(reference())

    async def test_application_cleanup_preserves_all_faults_and_releases_playing(self):
        session = FriendsSession.__new__(FriendsSession)
        session.application = self.app
        session.identity = dict(id=2)
        session.released = False
        session._aux_local_live = True
        self.app.playing[2] = session
        self.app._aux_local_sessions.add(session)
        errors = [ValueError('guild'), ValueError('shadow'), ValueError('mount'), ValueError('timer')]
        called = []
        def fail(index):
            called.append(index)
            raise errors[index]
        session.activity2026_awards = SimpleNamespace(online=SimpleNamespace(observe=lambda *a, **k: fail(3)))
        self.app.world = SimpleNamespace(disconnect=lambda s: called.append('world'))
        with patch('els_server.domain.guild_agit_flow.disconnect', lambda s: fail(0)), \
             patch('els_server.domain.tenebros_storage_flow.abandon', lambda s: fail(1)), \
             patch('els_server.domain.mount_flow.close', lambda s: fail(2)):
            with self.assertRaises(BaseExceptionGroup) as caught:
                await self.app.release(session)
        self.assertEqual(leaves(caught.exception), errors)
        self.assertEqual(called, [0, 1, 2, 3, 'world'])
        self.assertTrue(session.released)
        self.assertFalse(session._aux_local_live)
        self.assertNotIn(session, self.app._aux_local_sessions)
        self.assertNotIn(2, self.app.playing)

    def gateway(self):
        self.app.registry = SimpleNamespace(authenticate=lambda *a: dict(id=2, name='synthetic'))
        return AccountGateway(self.app.config, self.app)

    def document(self):
        return dict(op='tutorial_recovery_confirm', name='synthetic', token='t'*32,
                    uid=1001, version='0'*64, operation_id='00000000-0000-4000-8000-000000000001')

    def prepare_ticket(self, path, account_id, uid, version, operation, generation, stop):
        now = time.monotonic()
        return recovery.PreparationTicket(Path(path), self.path.parent/'backup', account_id, uid,
            operation, version, 'a'*64, (uid,20000,0,0,0.,0.,0.,0), generation, now, now+15, stop)

    async def test_recovery_ticket_pins_root_through_cancelled_socket_and_backup(self):
        root = Root()
        self.app.accounts[2] = root
        reference = weakref.ref(root)
        gateway = self.gateway()
        entered, gate = threading.Event(), threading.Event()
        self.addCleanup(gate.set)
        def backup(ticket):
            entered.set()
            gate.wait(3)
            return 'owned-backup'
        finished = []
        def finish(ticket, backup_name, guard):
            guard()
            finished.append(ticket.account_id)
            return dict(ok=True)
        with patch.object(recovery, 'prepare', self.prepare_ticket), \
             patch.object(recovery, 'backup_ticket', backup), patch.object(recovery, 'finish', finish), \
             patch.object(gateway, '_refresh_recovery', lambda ticket: None):
            caller = asyncio.create_task(gateway.recovery(self.document(), 'owned-host'))
            await asyncio.to_thread(entered.wait, 2)
            self.assertEqual(len(gateway.recovery_pins), 1)
            caller.cancel()
            await asyncio.gather(caller, return_exceptions=True)
            del root
            gc.collect()
            self.assertIsNotNone(reference())
            gate.set()
            flight = next(iter(gateway.recovery_flights.values()))['task']
            self.assertEqual(await flight, dict(ok=True))
            self.assertEqual(finished, [2])
            await self.app.call(lambda: None)
            del caller, flight
            gc.collect()
            self.assertIsNone(reference())
            self.assertEqual(len(gateway.recovery_pins), 0)
        await gateway.close()

    async def test_recovery_pin_does_not_hide_root_replacement_or_failed_preparation(self):
        root = Root()
        self.app.accounts[2] = root
        gateway = self.gateway()
        with patch.object(recovery, 'prepare', self.prepare_ticket):
            ticket = await self.app.call(gateway._prepare_recovery, self.document(), 'owned-host')
        self.assertEqual(len(gateway.recovery_pins), 1)
        replacement = Root()
        self.app.accounts[2] = replacement
        with self.assertRaisesRegex(recovery.RecoveryError, 'recovery_stale'):
            await self.app.call(gateway._finish_recovery, self.document(), ticket, 'owned-backup')
        del ticket
        await self.app.call(lambda: None)
        gc.collect()
        self.assertEqual(len(gateway.recovery_pins), 0)
        def fail(*args):
            raise recovery.RecoveryError('recovery_stale')
        with patch.object(recovery, 'prepare', fail):
            with self.assertRaises(recovery.RecoveryError):
                await self.app.call(gateway._prepare_recovery, self.document(), 'owned-host')
        self.assertEqual(len(gateway.recovery_pins), 0)

    async def test_real_owned_recovery_backup_commit_replay_and_cold_read(self):
        import sqlite3
        from contextlib import closing
        from els_server.domain.local_session import LocalAccount
        from els_server.storage.local_state import LocalState
        from els_server.storage.accounts import Accounts
        seed = LocalAccount(LocalState(self.path))
        seed.enable_characters()
        registry = Accounts(self.path.with_name('accounts.sqlite3'))
        self.app.registry = registry
        identity = registry.create('owned_recovery')
        self.assertEqual(identity['id'], 2)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE character_owners SET account_id=2 WHERE uid=1001')
            db.execute("UPDATE characters SET unit_type=13,unit_class=203,name='RecoveryRole',name_key='recoveryrole' WHERE uid=1001")
        session = await self.app.session(identity=identity)
        root = session.account
        reference = weakref.ref(root)
        gateway = AccountGateway(self.app.config, self.app)
        preview = await self.app.call(recovery.preview, self.path, 2, 0)
        descriptor = preview['characters'][0]
        document = self.document()
        document.update(name=identity['name'], token=identity['token'], version=descriptor['version'])
        first = await gateway.recovery(document, 'owned-host')
        self.assertTrue(first['ok'], first)
        self.assertFalse(first['replayed'])
        self.assertEqual(root.location['map'], descriptor['target_town'])
        self.assertEqual(LocalState(self.path, 1001).load()['map'], descriptor['target_town'])
        backup = self.path.parent/'backups/tutorial-recovery'/first['backup']
        self.assertTrue(backup.is_file())
        with closing(sqlite3.connect(backup)) as db:
            self.assertEqual(db.execute('SELECT town FROM location WHERE uid=1001').fetchone(), (20000,))
        replayed = await gateway.recovery(dict(document), 'owned-host')
        self.assertTrue(replayed['ok'])
        self.assertTrue(replayed['replayed'])
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM tutorial_recovery_receipts').fetchone(), (1,))
        await self.app.release(session)
        del session, root
        await self.app.call(lambda: None)
        gc.collect()
        self.assertIsNone(reference())
        cold = await self.app.session(identity=identity)
        self.assertEqual(cold.account.location['map'], descriptor['target_town'])
        await gateway.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
