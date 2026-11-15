"""Cooperative time slices on the existing single business worker.

A member remains indivisible: its transaction, read scope and clock observations
finish before a slice is returned. Room polling is shared across the cohort.
"""
import math
import time


async def periodic_chunks(application, sessions, *, budget_ms=4.0):
    from els_server.application import FriendsSession
    sessions = tuple(sessions)
    if len(sessions) > 16:
        raise ValueError('Periodic batch bounds')
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
            while position < len(sessions):
                session = sessions[position]
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

        yield await application.business_queue.run(invoke, timing=queue_timing)
