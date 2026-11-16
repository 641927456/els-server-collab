"""Record server-observed anomalies for operator review."""
from collections import Counter, deque
from contextlib import contextmanager
from contextvars import ContextVar
import json
from threading import Lock
from time import monotonic


EVENT = 'anti_cheat_signal'
FILENAME = 'anti-cheat.jsonl'
_dungeon_request = ContextVar('anti_cheat_dungeon_request', default=None)


class AntiCheat:
    def __init__(self, log, min_clear_seconds, *, now=monotonic):
        self.log = log
        self.min_clear_seconds = min_clear_seconds
        self.now = now
        self.lock = Lock()
        self.window = None
        self.counts = Counter()
        self.total = 0
        self._saturated_window = None

    def record(self, rule, account_id, *, scope, **details):
        # The limits bound evidence volume even when an account reconnects or
        # changes rooms. Each accepted sample has fixed-size scalar fields.
        saturated = self._saturated_window
        if saturated is not None and saturated == int(self.now() // 60):
            return
        with self.lock:
            window = int(self.now() // 60)
            if window != self.window:
                self.window = window
                self.counts.clear()
                self.total = 0
                self._saturated_window = None
            key = (account_id, rule)
            if self.total >= 120 or self.counts[key] >= 3:
                return
            self.counts[key] += 1
            self.total += 1
            if self.total == 120:
                self._saturated_window = window
        self.log(EVENT, rule=rule, scope=scope, account_id=account_id, **details)

    @contextmanager
    def dungeon_request(self, session, sequence, received=None):
        run = session.dungeon_run
        map_id, stage, part, run_id = ((run.identity,run.stage,run.part,run.run_id)
            if run is not None else (session.dungeon_id,session.gate_stage,0,session.reward_run_id))
        token = _dungeon_request.set((self, session.identity, session.reward_run_id, received,
            session.account.uid, run_id, map_id, stage, part, sequence))
        try:
            yield
            if self.min_clear_seconds and session.clear_notified and not session.dungeon_failed:
                self._clear_signal(session, map_id)
        finally:
            _dungeon_request.reset(token)

    def _clear_signal(self, session, map_id):
        minimum = self.min_clear_seconds.get(map_id)
        receipt = session.reward_receipt
        if (minimum is not None and receipt and receipt.get('replayed') is False
                and receipt.get('run_id') == session.reward_run_id):
            assessment = receipt.get('local_rules')
            if assessment is not None:
                elapsed = assessment['assessment']['seconds']
                if elapsed < minimum:
                    dungeon_signal(session, 'short_clear_time', outcome='settled',
                                   elapsed_seconds=elapsed, minimum_seconds=minimum)


def dungeon_signal(session, rule, *, outcome='rejected', **details):
    request = _dungeon_request.get()
    if request is None:
        return
    detector, identity, reward_run_id, _, uid, run_id, map_id, stage, part, sequence = request
    # Transactional shadows retain the initiating identity. A member processed
    # during shared settlement must not be blamed for the initiator's input.
    if getattr(session, 'identity', None) is identity and session.reward_run_id == reward_run_id:
        detector.record(rule, identity['id'], scope='dungeon', outcome=outcome,
                        character_id=uid, run_id=run_id, map_id=map_id, stage=stage, part=part,
                        request_sequence=sequence, **details)


def summon_received(session):
    request = _dungeon_request.get()
    if request is not None and request[1] is session.identity and request[2] == session.reward_run_id:
        return request[3]
    return None


def pvp_signal(session, room, sequence, rule):
    detector = getattr(getattr(session, 'application', None), 'anti_cheat', None)
    if detector is not None:
        detector.record(rule, session.identity['id'], scope='pvp', outcome='rejected',
                        character_id=session.account.uid, run_id=room.seed, map_id=room.map_id,
                        request_sequence=sequence)


def recent_signals(log_dir, backups, *, account_id=None, run_id=None, limit=50):
    matches = deque(maxlen=limit)
    base = log_dir / FILENAME
    rotated = (base.with_name(f'{base.name}.{index}') for index in range(backups, 0, -1))
    for path in (*rotated, base):
        try:
            source = path.open(encoding='utf8')
        except FileNotFoundError:
            continue
        with source:
            for line in source:
                if not line.endswith('\n'):
                    # A live writer may not have completed the final record.
                    continue
                row = json.loads(line)
                if ((account_id is None or row['account_id'] == account_id)
                        and (run_id is None or row.get('run_id') == run_id)):
                    matches.append(row)
    return reversed(matches)
