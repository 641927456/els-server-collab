"""Cooperative time slices on the existing single business worker.

A member remains indivisible: its transaction, read scope and clock observations
finish before a slice is returned. Room polling is shared across the cohort.
"""
import math
import time
from threading import Lock


class PeriodicClaim:
    """Cancel only an unstarted poll, never its SQL or native delivery."""
    def __init__(self):self.lock=Lock();self.state='pending'
    def start(self):
        with self.lock:
            if self.state!='pending':return False
            self.state='running';return True
    def cancel(self):
        with self.lock:
            if self.state!='pending':return False
            self.state='cancelled';return True
    @property
    def cancelled(self):
        with self.lock:return self.state=='cancelled'


async def periodic_chunks(application, sessions, *, budget_ms=4.0, claims=None):
    from els_server.application import FriendsSession
    sessions = tuple(sessions)
    if len(sessions) > 16:
        raise ValueError('Periodic batch bounds')
    if claims is not None and len(claims)!=len(sessions):raise ValueError('Periodic claim bounds')
    if isinstance(budget_ms, bool) or not math.isfinite(budget_ms) or budget_ms <= 0:
        raise ValueError('Periodic slice budget')
    rooms = set()
    position = 0
    while position < len(sessions):
        submitted = time.perf_counter()
        queue_timing = {}

        def invoke():
            nonlocal position
            queue_timing['batch_started_at'] = time.perf_counter()
            deadline = time.monotonic() + budget_ms / 1000
            result = []
            try:
                while position < len(sessions):
                    session = sessions[position]
                    if claims is not None and not claims[position].start():
                        result.append(([],None));position+=1
                        continue
                    options = {'_rooms': rooms} if isinstance(session, FriendsSession) else {}
                    try:
                        messages = application._worker_call(session.periodic_notifications, (), options,
                                                            submitted, queue_timing=queue_timing)
                        result.append((messages, None))
                    except Exception as error:
                        result.append((None, error))
                    position += 1
                    if time.monotonic() >= deadline:
                        break
                return result

            finally:application.realtime.publish(application,invoke,(),periodic=True)

        yield await application.business_queue.run(invoke, timing=queue_timing)
