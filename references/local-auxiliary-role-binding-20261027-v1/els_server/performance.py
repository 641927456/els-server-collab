"""Bounded server-side timings. No payload, account identity, or SQL text."""
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
import threading
import time

_capture = ContextVar('server_call_capture', default=None)
_active = ContextVar('server_worker_timing', default=None)


@contextmanager
def capture_calls():
    calls = []
    token = _capture.set(calls)
    try:
        yield calls
    finally:
        _capture.reset(token)


def captured_calls():
    return _capture.get()


@contextmanager
def worker_timing(sample):
    token = _active.set(sample)
    try:
        yield
    finally:
        _active.reset(token)


def projection_loaded(seconds, hit=False):
    sample = _active.get()
    if sample is not None:
        sample['projection_ms'] += seconds * 1000
        sample['projection_hits' if hit else 'projection_loads'] += 1


def registry_checked(seconds):
    sample = _active.get()
    if sample is not None:
        sample['registry_ms'] += seconds * 1000
        sample['registry_checks'] += 1


class OperationMetrics:
    """Exact counters/maxima plus the last 256 operations per fixed category."""
    def __init__(self):
        self.lock = threading.Lock()
        self.groups = {}
        self.next_report = time.monotonic() + 60

    def record(self, name, sample):
        category = name if name in ('handle', 'periodic_notifications', 'authenticate') else 'other'
        with self.lock:
            group = self.groups.setdefault(category, dict(count=0, errors=0, queue_max_ms=0,
                handler_max_ms=0, samples=deque(maxlen=256)))
            group['count'] += 1
            group['errors'] += int(sample['failed'])
            for key in ('queue_ms', 'handler_ms'):
                maximum = key.replace('_ms', '_max_ms')
                group[maximum] = max(group[maximum], sample[key])
            group['samples'].append(dict(sample))

    def due(self):
        now = time.monotonic()
        with self.lock:
            if now < self.next_report:
                return None
            self.next_report = now + 60
        return self.snapshot()

    def snapshot(self):
        with self.lock:
            result = {}
            for category, group in self.groups.items():
                samples = group['samples']
                row = {k: v for k, v in group.items() if k != 'samples'}
                row['window_count'] = len(samples)
                for key in ('queue_ms', 'handler_ms', 'projection_ms'):
                    values = sorted(s[key] for s in samples)
                    row[key + '_p95'] = round(values[max(0, (95 * len(values) + 99) // 100 - 1)], 3)
                result[category] = row
            return result


def local_auxiliary_noop(session, event):
    """The existing nine-byte DX11 no-op, only in a live owned LOCAL actor."""
    if not (event.event_id == 0x202 and event.kind == 0x7d0
            and event.performers == (0,) and event.uid == event.target_uid == 2**64-1
            and event.payload_mode == 0 and len(event.payload) == 9
            and session.client_build == 'dx11_260923' and session.role == 'game'
            and session.phase in ('town_ready', 'dungeon_active')):
        return False
    application = getattr(session, '_aux_local_application', None)
    account = session.account
    if application is None or application.config.mode != 'local':
        return False
    owner = application.account
    bound = account is owner or (
        getattr(account, 'root', None) is owner and owner.characters is not None
        and owner.character_accounts.get(account.uid) is account
        and account.characters is owner.characters and account.account_id == owner.account_id
        and account.store is not None and owner.store is not None
        and account.store.path == owner.store.path)
    return bool(bound and getattr(session, '_aux_local_live', False)
        and session in application._aux_local_sessions
        and account.store is not None and account.store.uid == account.uid
        and sum(s.role == 'game' and s.phase in ('town_ready', 'dungeon_active')
                for s in application._aux_local_sessions) == 1)
