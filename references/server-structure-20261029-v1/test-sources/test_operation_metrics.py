"""Task-owned metrics tests: deterministic clocks, no server or player database."""
import asyncio
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

TASK = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ['ELS_RUNTIME_ROOT']).resolve()
if RUNTIME not in ((TASK / 'runtimes/online').resolve(), (TASK / 'runtimes/local').resolve()):
    raise RuntimeError('Only this task owned materialized runtimes are permitted')
sys.path.insert(0, str(RUNTIME))
from els_server import application, business_queue, performance, periodic_scheduler
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.performance import OperationMetrics, capture_calls, request_category
from els_server.periodic_scheduler import PeriodicScheduler

SOURCE_SHA = {}
for module in (application, business_queue, performance, periodic_scheduler):
    relative = Path('els_server') / Path(module.__file__).name
    source = RUNTIME / relative
    candidate = TASK / 'candidate' / RUNTIME.name / relative
    if Path(module.__file__).resolve() != source or source.read_bytes() != candidate.read_bytes():
        raise RuntimeError('Imported runtime must exactly match this channel candidate')
    SOURCE_SHA[str(relative)] = sha256(source.read_bytes()).hexdigest()


class Actor:
    phase = 'initialization_confirmed'

    def handle(self, event):
        self.phase = 'dungeon_active'
        return [event.kind]

    def periodic_notifications(self):
        return [self.phase]


def event(kind, event_id=0x202):
    # These synthetic identity/payload values must never become metric labels.
    return SimpleNamespace(event_id=event_id, kind=kind, uid='private-test-uid',
                           payload=b'private-test-payload')


def sample(value=1):
    return dict(queue_ms=value, admission_ms=value / 4, executor_ms=value / 2,
                batch_wait_ms=value / 4, handler_ms=value * 2, failed=False)


class CategoryTests(unittest.TestCase):
    def test_explicit_current_routes_and_phase_limits(self):
        actor = Actor()
        self.assertEqual(request_category(actor.handle, (event(0x28),)), 'selection')
        for phase in ('initialization_confirmed', 'map_loading', 'square_accepted', 'town_ready'):
            actor.phase = phase
            for kind in (0x32, 0x225, 0x227):
                self.assertEqual(request_category(actor.handle, (event(kind),)), 'town')
        for phase in ('dungeon_active', 'guild_agit_loading', 'characters_ready', None):
            actor.phase = phase
            for kind in (0x32, 0x225, 0x227):
                self.assertEqual(request_category(actor.handle, (event(kind),)), 'other')
        for kind in (0xEA, 0x567, 0x80F):
            self.assertEqual(request_category(actor.handle, (event(kind),)), 'economy')
        # The economy category is intentionally only this known subset.
        for kind in (0x60, 0x999, 0x7D0):
            self.assertEqual(request_category(actor.handle, (event(kind),)), 'other')

    def test_unknown_types_namespaces_and_non_requests_are_bounded(self):
        actor = Actor()
        for value in (None, True, '40', [], {}, 40.0):
            self.assertEqual(request_category(actor.handle, (event(value),)), 'other')
            self.assertEqual(request_category(actor.handle, (event(0x28, value),)), 'other')
        self.assertEqual(request_category(actor.handle, (event(0x28, 0x203),)), 'other')
        self.assertEqual(request_category(actor.handle, (object(),)), 'other')
        self.assertEqual(request_category(actor.handle, ()), 'other')
        self.assertIsNone(request_category(actor.periodic_notifications, ()))

    def test_request_and_legacy_windows_keep_fixed_cardinality(self):
        metrics = OperationMetrics()
        for i in range(1000):
            metrics.record('untrusted-operation-%s' % i, sample(i), request='private-label-%s' % i)
        for category in ('selection', 'town', 'economy', 'other'):
            metrics.record('handle', sample(), request=category)
        metrics.record('periodic_notifications', sample())
        metrics.record('authenticate', sample())
        metrics.record('handle', sample(), request=[])
        old = metrics.snapshot()
        requests = metrics.request_snapshot()
        self.assertEqual(set(old), {'handle', 'periodic_notifications', 'authenticate', 'other'})
        self.assertEqual(set(requests), {'selection', 'town', 'economy', 'other'})
        self.assertEqual(old['other']['count'], 1000)
        self.assertEqual(old['other']['window_count'], 256)
        self.assertEqual(old['other']['queue_ms_p95'], 987)
        self.assertEqual(old['other']['queue_max_ms'], 999)
        self.assertEqual(requests['other']['count'], 1002)
        self.assertEqual(requests['other']['window_count'], 256)
        for row in (*old.values(), *requests.values()):
            self.assertLessEqual(row['window_count'], 256)
            for name in ('queue_ms_p95', 'admission_ms_p95', 'executor_ms_p95', 'batch_wait_ms_p95'):
                self.assertIn(name, row)
        self.assertNotIn('private-', json.dumps({'operations': old, 'requests': requests}))


class ApplicationTimingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = Application(ServerConfig(profile='bootstrap'))
        self.addCleanup(self.app.close)

    def assert_waits(self, observed, admission, executor, batch, total):
        self.assertEqual(observed['admission_ms'], admission)
        self.assertEqual(observed['executor_ms'], executor)
        self.assertEqual(observed['batch_wait_ms'], batch)
        self.assertEqual(observed['queue_ms'], total)
        self.assertEqual(sum(observed[key] for key in ('admission_ms', 'executor_ms', 'batch_wait_ms')), total)

    async def test_real_call_plumbs_admission_and_captures_entry_phase(self):
        actor = Actor()
        with patch.object(application, 'time', SimpleNamespace(perf_counter=Mock(side_effect=[10., 20., 23.]))), \
             patch.object(business_queue, 'time', SimpleNamespace(perf_counter=lambda: 12.)), capture_calls() as calls:
            result = await self.app.call(actor.handle, event(0x225))
        self.assertEqual(result, [0x225])
        self.assertEqual(actor.phase, 'dungeon_active')
        self.assertEqual(len(calls), 1)
        self.assert_waits(calls[0], 2000, 8000, 0, 10000)
        self.assertEqual(calls[0]['handler_ms'], 3000)
        self.assertFalse(calls[0]['failed'])
        self.assertEqual(set(self.app.performance.request_snapshot()), {'town'})
        self.assertEqual(self.app.performance.snapshot()['handle']['count'], 1)
        self.assertNotIn('private-', json.dumps(calls))

    async def test_real_periodic_batch_separates_each_members_wait(self):
        actors = (Actor(), Actor())
        clock = Mock(side_effect=[10., 15., 20., 23., 30., 34.])
        with patch.object(application, 'time', SimpleNamespace(perf_counter=clock)), \
             patch.object(business_queue, 'time', SimpleNamespace(perf_counter=lambda: 12.)):
            result = await self.app.periodic_batch(actors)
        self.assertEqual(result, [(['initialization_confirmed'], None)] * 2)
        observed = list(self.app.performance.groups['periodic_notifications']['samples'])
        self.assert_waits(observed[0], 2000, 3000, 5000, 10000)
        self.assert_waits(observed[1], 2000, 3000, 15000, 20000)
        self.assertEqual([row['handler_ms'] for row in observed], [3000, 4000])
        self.assertEqual(self.app.performance.request_snapshot(), {})

    async def test_failed_call_preserves_error_and_wait_observation(self):
        error = ValueError('synthetic failure')
        def fail():
            raise error
        with patch.object(application, 'time', SimpleNamespace(perf_counter=Mock(side_effect=[10., 20., 24.]))), \
             patch.object(business_queue, 'time', SimpleNamespace(perf_counter=lambda: 12.)), capture_calls() as calls:
            with self.assertRaises(ValueError) as caught:
                await self.app.call(fail)
        self.assertIs(caught.exception, error)
        self.assertTrue(calls[0]['failed'])
        self.assert_waits(calls[0], 2000, 8000, 0, 10000)
        self.assertEqual(self.app.performance.snapshot()['other']['errors'], 1)


class SchedulerMetricTests(unittest.IsolatedAsyncioTestCase):
    async def test_due_selection_and_summary_keep_legacy_and_new_contract(self):
        metrics = OperationMetrics()
        metrics.record('handle', sample(5), request='selection')
        metrics.next_report = 0
        queue = dict(capacity=16, inflight=2, waiting=3, maximum=8, waiting_maximum=9,
                     completed=4, closed=False)
        app = SimpleNamespace(performance=metrics, preparation=SimpleNamespace(snapshot=lambda: {}),
                              business_queue=SimpleNamespace(snapshot=lambda: dict(queue)))
        logs = []
        scheduler = PeriodicScheduler(app, .5, lambda name, **fields: logs.append((name, fields)))
        sent = []
        async def deliver(messages):
            sent.append(messages)
        async def batch(sessions):
            scheduler.closing = True
            return [([session], None) for session in sessions]
        app.periodic_batch = batch
        loop = asyncio.get_running_loop()
        slots = [SimpleNamespace(session=i, operation=asyncio.Lock(), send=deliver,
                                 due=due, closed=False, finished=None, failure=loop.create_future())
                 for i, due in enumerate((95., 98.))]
        scheduler.slots = {i: slot for i, slot in enumerate(slots)}
        with patch.object(periodic_scheduler, 'time', SimpleNamespace(monotonic=lambda: 100.)):
            await scheduler._run()
            await asyncio.gather(*scheduler.deliveries)
        self.assertEqual(sent, [[0], [1]])
        self.assertTrue(all(not slot.operation.locked() for slot in slots))
        self.assertTrue(all(slot.due == 100.5 for slot in slots))
        self.assertEqual(len(logs), 1)
        name, fields = logs[0]
        self.assertEqual(name, 'application_timing_summary')
        self.assertEqual(set(fields), {'operations', 'requests', 'business_queue', 'periodic', 'preparation'})
        self.assertEqual(fields['business_queue'], queue)
        self.assertEqual(fields['operations']['handle']['queue_ms_p95'], 5)
        self.assertEqual(fields['requests']['selection']['count'], 1)
        self.assertEqual(fields['periodic']['dispatch_late_max_ms'], 5000)
        self.assertEqual(fields['periodic']['dispatch_late_ms_p95'], 5000)
        self.assertEqual(fields['periodic']['dispatch_late_window_count'], 2)

    async def test_lateness_window_stays_bounded_and_empty_snapshot_is_defined(self):
        scheduler = PeriodicScheduler(SimpleNamespace(), .5, lambda *a, **k: None)
        self.assertEqual(scheduler.snapshot()['dispatch_late_ms_p95'], 0)
        self.assertEqual(scheduler.snapshot()['dispatch_late_window_count'], 0)
        for value in range(1000):
            scheduler.dispatch_lateness.append(value)
        observed = scheduler.snapshot()
        self.assertEqual(observed['dispatch_late_window_count'], 256)
        self.assertEqual(observed['dispatch_late_ms_p95'], 987)


if __name__ == '__main__':
    print(json.dumps({'runtime': str(RUNTIME), 'source_sha256': SOURCE_SHA}, sort_keys=True))
    unittest.main(verbosity=2)
