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


def sqlite_observed(*,wait=None,held=None,finish=None,busy=False,finish_busy=False,rollback=False):
    sample=_active.get()
    if sample is None:return
    for key,value in (('sql_begin_wait_ms',wait),('sql_writer_held_ms',held),('sql_finish_wait_ms',finish)):
        if value is not None:sample[key]=sample.get(key,0.)+value*1000
    sample['sql_finish_busy']=sample.get('sql_finish_busy',0)+int(finish_busy)
    sample['sql_busy']=sample.get('sql_busy',0)+int(busy)
    sample['sql_rollbacks']=sample.get('sql_rollbacks',0)+int(rollback)



# These are observation categories, never admission/authorization decisions.
# LocalSession's current 0x202 routes: selection 0x28; ordinary town
# initialization 0x32/225/227; NPC buy/repurchase 0xEA/567 and ED shop 0x80F.
# Other economic features deliberately remain "other" until mapped explicitly.
REQUEST_CATEGORIES = frozenset(('selection', 'town', 'economy', 'other'))
WAIT_METRICS = ('queue_ms', 'admission_ms', 'executor_ms', 'batch_wait_ms')


def request_category(function, args):
    if getattr(function, '__name__', None) != 'handle':
        return None
    if not args:
        return 'other'
    event = args[0]
    event_id = getattr(event, 'event_id', None)
    kind = getattr(event, 'kind', None)
    if type(event_id) is not int or event_id != 0x202 or type(kind) is not int:
        return 'other'
    if kind == 0x28:
        return 'selection'
    phase = getattr(getattr(function, '__self__', None), 'phase', None)
    if kind in (0x32, 0x225, 0x227) and phase in (
            'initialization_confirmed', 'map_loading', 'square_accepted', 'town_ready'):
        return 'town'
    if kind in (0xEA, 0x567, 0x80F):
        return 'economy'
    return 'other'


class OperationMetrics:
    """Bounded legacy operation groups and four separate native request groups."""
    def __init__(self):
        self.lock = threading.Lock()
        self.groups = {}
        self.request_groups = {}
        self.next_report = time.monotonic() + 60

    @staticmethod
    def _record(groups, category, sample):
        group = groups.setdefault(category, dict(count=0, errors=0, queue_max_ms=0,
            handler_max_ms=0, samples=deque(maxlen=256)))
        group['count'] += 1
        group['errors'] += int(sample['failed'])
        for key in ('sql_busy', 'sql_finish_busy', 'sql_rollbacks'):
            group[key] = group.get(key, 0) + sample.get(key, 0)
        for key in WAIT_METRICS + ('handler_ms',):
            maximum = key.replace('_ms', '_max_ms')
            group[maximum] = max(group.get(maximum, 0), sample.get(key, 0))
        group['samples'].append(dict(sample))

    def record(self, name, sample, *, request=None):
        category = name if name in ('handle', 'periodic_notifications', 'authenticate') else 'other'
        with self.lock:
            self._record(self.groups, category, sample)
            if request is not None:
                category = request if type(request) is str and request in REQUEST_CATEGORIES else 'other'
                self._record(self.request_groups, category, sample)

    def due(self):
        now = time.monotonic()
        with self.lock:
            if now < self.next_report:
                return None
            self.next_report = now + 60
        return self.snapshot()

    @staticmethod
    def _snapshot(groups):
        result = {}
        for category, group in groups.items():
            samples = group['samples']
            row = {k: v for k, v in group.items() if k != 'samples'}
            row['window_count'] = len(samples)
            for key in WAIT_METRICS + ('handler_ms', 'projection_ms', 'sql_begin_wait_ms', 'sql_finish_wait_ms', 'sql_writer_held_ms'):
                values = sorted(s.get(key, 0.) for s in samples)
                row[key + '_p95'] = round(values[max(0, (95 * len(values) + 99) // 100 - 1)], 3)
            result[category] = row
        return result

    def snapshot(self):
        # Preserve the legacy operation names and fields for existing readers.
        with self.lock:
            return self._snapshot(self.groups)

    def request_snapshot(self):
        with self.lock:
            return self._snapshot(self.request_groups)


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
