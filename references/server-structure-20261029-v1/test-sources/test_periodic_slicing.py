"""Deterministic gates and clocks for worker fairness and delivery ownership."""
import asyncio
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from els_server.application import Application, FriendsSession
from els_server.config import ServerConfig
from els_server.periodic_scheduler import PeriodicScheduler
from els_server import periodic_work


class Actor:
    def __init__(self, function):
        self.function = function

    def periodic_notifications(self):
        return self.function()


class PeriodicSlicingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = Application(ServerConfig(profile='bootstrap'))
        self.addCleanup(self.app.close)

    async def test_fast_cohort_retains_one_submission(self):
        actors = [Actor(lambda: [7]) for _ in range(16)]
        with patch.object(periodic_work, 'time', SimpleNamespace(monotonic=lambda: 0., perf_counter=time.perf_counter)):
            chunks = [c async for c in periodic_work.periodic_chunks(self.app, actors)]
        self.assertEqual(chunks, [[([7], None)] * 16])
        async with asyncio.timeout(2):
            while self.app.business_queue.completed != 1:
                await asyncio.sleep(0)
        self.assertEqual(self.app.business_queue.completed, 1)
        self.assertEqual(self.app.performance.snapshot()['periodic_notifications']['count'], 16)

    async def test_budget_boundary_yields_and_keeps_order_and_errors(self):
        now = [0.]
        failure = ValueError('member failure')
        def member(index):
            now[0] += .003
            if index == 2:
                raise failure
            return [index]
        actors = [Actor(lambda i=i: member(i)) for i in range(5)]
        with patch.object(periodic_work, 'time', SimpleNamespace(monotonic=lambda: now[0], perf_counter=time.perf_counter)):
            iterator = periodic_work.periodic_chunks(self.app, actors)
            first = await anext(iterator)
            self.assertEqual(first, [([0], None), ([1], None)])
            self.assertEqual(await self.app.call(lambda: 99), 99)
            rest = [c async for c in iterator]
        self.assertEqual([len(first)] + [len(c) for c in rest], [2, 2, 1])
        self.assertIs(rest[0][0][1], failure)
        self.assertEqual(rest[0][1], ([3], None))
        self.assertEqual(rest[1], [([4], None)])

    async def test_rooms_and_read_scopes_survive_slice_boundary(self):
        now = [0.]
        rooms = []
        scopes = []
        from els_server.storage.read_scope import _current
        class Member(FriendsSession):
            def __init__(self):
                self.activity2026_awards = None
            def periodic_notifications(self, *, _rooms):
                now[0] += .01
                rooms.append(_rooms)
                scopes.append(_current.get())
                result = [len(_rooms)]
                _rooms.add('shared-room')
                return result
        with patch.object(periodic_work, 'time', SimpleNamespace(monotonic=lambda: now[0], perf_counter=time.perf_counter)):
            chunks = [c async for c in periodic_work.periodic_chunks(self.app, [Member(), Member()])]
        self.assertEqual(chunks, [[([0], None)], [([1], None)]])
        self.assertIs(rooms[0], rooms[1])
        self.assertIsNot(scopes[0], scopes[1])
        self.assertTrue(all(s is not None for s in scopes))

    async def test_slow_later_member_does_not_hold_completed_delivery(self):
        entered = threading.Event()
        gate = threading.Event()
        order = []
        def fast():
            order.append('fast-work')
            return ['fast']
        def slow():
            entered.set()
            if not gate.wait(3):
                raise TimeoutError('test gate')
            order.append('slow-work')
            return ['slow']
        actors = [Actor(fast), Actor(slow)]
        self.app.periodic_chunks = lambda sessions: periodic_work.periodic_chunks(self.app, sessions, budget_ms=.000001)
        scheduler = PeriodicScheduler(self.app, 60, lambda *a, **k: None)
        loop = asyncio.get_running_loop()
        locks = [asyncio.Lock(), asyncio.Lock()]
        fast_sent = asyncio.Event()
        async def send(messages):
            order.append(messages[0] + '-send')
            if messages == ['fast']:
                fast_sent.set()
        slots = [SimpleNamespace(session=s, operation=locks[i], send=send, due=0.,
                                 closed=False, finished=None, failure=loop.create_future())
                 for i,s in enumerate(actors)]
        scheduler.slots = dict(enumerate(slots))
        scheduler.task = asyncio.create_task(scheduler._run())
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 2))
            await asyncio.wait_for(fast_sent.wait(), 2)
            self.assertEqual(order, ['fast-work', 'fast-send'])
            self.assertFalse(locks[0].locked())
            self.assertTrue(locks[1].locked())
        finally:
            gate.set()
            await scheduler.close()
        self.assertEqual(order, ['fast-work', 'fast-send', 'slow-work', 'slow-send'])
        self.assertTrue(all(not lock.locked() for lock in locks))

    async def test_later_admission_failure_only_fails_remaining_member(self):
        scheduler = PeriodicScheduler(self.app, 60, lambda *a, **k: None)
        failure = RuntimeError('queue closed')
        async def chunks(sessions):
            yield [(['first'], None)]
            scheduler.closing = True
            raise failure
        self.app.periodic_chunks = chunks
        loop = asyncio.get_running_loop()
        sent = []
        async def send(messages):
            sent.append(messages)
        slots = [SimpleNamespace(session=i, operation=asyncio.Lock(), send=send,
                                 due=0., closed=False, finished=None, failure=loop.create_future()) for i in range(2)]
        scheduler.slots = dict(enumerate(slots))
        await scheduler._run()
        await asyncio.gather(*scheduler.deliveries)
        self.assertEqual(sent, [['first']])
        self.assertFalse(slots[0].failure.done())
        self.assertIs(slots[1].failure.exception(), failure)
        self.assertTrue(all(not s.operation.locked() for s in slots))

    async def test_disconnect_during_real_slice_waits_and_drops_its_reply(self):
        entered = threading.Event()
        gate = threading.Event()
        def work():
            entered.set()
            if not gate.wait(3):
                raise TimeoutError('test gate')
            return ['closed-member']
        scheduler = PeriodicScheduler(self.app, .01, lambda *a, **k: None)
        lock = asyncio.Lock()
        sent = []
        async def send(messages):
            sent.append(messages)
        task = asyncio.create_task(scheduler.serve(Actor(work), lock, send))
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 2))
            task.cancel()
            await asyncio.sleep(.01)
            self.assertFalse(task.done())
            self.assertTrue(lock.locked())
            gate.set()
            await asyncio.gather(task, return_exceptions=True)
            self.assertFalse(lock.locked())
            self.assertEqual(sent, [])
        finally:
            gate.set()
            await asyncio.gather(task, return_exceptions=True)
            await scheduler.close()

    async def test_bounds_empty_and_budget_validation(self):
        self.assertEqual([c async for c in periodic_work.periodic_chunks(self.app, [])], [])
        for budget in (0., -1., float('inf'), float('nan'), True):
            with self.assertRaises(ValueError):
                _ = [c async for c in periodic_work.periodic_chunks(self.app, [], budget_ms=budget)]
        with self.assertRaises(ValueError):
            _ = [c async for c in periodic_work.periodic_chunks(self.app, [None]*17)]
