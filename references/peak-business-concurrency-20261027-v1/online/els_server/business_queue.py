"""Bound admission to the existing single worker, including cancelled jobs."""
import asyncio
from concurrent.futures import CancelledError
import threading


class BoundedBusinessQueue:
    def __init__(self, executor, capacity=16):
        if type(capacity) is not int or capacity < 1:
            raise ValueError('Business queue capacity')
        self.executor = executor
        self.capacity = capacity
        self.closed = False
        self.loop = None
        self.semaphore = None
        self.waiters = set()
        self.inflight = self.maximum = self.completed = 0

    async def run(self, function):
        loop = asyncio.get_running_loop()
        if self.closed:
            raise RuntimeError('Business queue is closed')
        if self.loop is not loop:
            if self.inflight or self.waiters:
                raise RuntimeError('Business queue belongs to another active loop')
            self.loop = loop
            self.semaphore = asyncio.Semaphore(self.capacity)
        # Track only the admission task: shutdown must not cancel a caller
        # whose SQL has already started and still needs to commit/rollback.
        waiter = loop.create_task(self.semaphore.acquire())
        self.waiters.add(waiter)
        try:
            await waiter
        except BaseException:
            # Cancellation can arrive after acquire completed but before this
            # coroutine resumed. Return that permit exactly once.
            if not waiter.cancelled() and waiter.done() and waiter.exception() is None:
                self.semaphore.release()
            raise
        finally:
            self.waiters.discard(waiter)
        if self.closed:
            self.semaphore.release()
            raise RuntimeError('Business queue is closed')
        state = dict(started=False, abandoned=False)
        lock = threading.Lock()

        def invoke():
            with lock:
                if state['abandoned']:
                    raise CancelledError()
                state['started'] = True
            return function()

        self.inflight += 1
        self.maximum = max(self.maximum, self.inflight)
        try:
            future = self.executor.submit(invoke)
        except BaseException:
            self.inflight -= 1
            self.semaphore.release()
            raise

        def retired():
            self.inflight -= 1
            self.completed += 1
            self.semaphore.release()

        def completed(_):
            # Only actual dequeue/completion returns capacity. Cancelling an
            # asyncio waiter must never admit more executor tombstones.
            if not loop.is_closed():
                loop.call_soon_threadsafe(retired)

        future.add_done_callback(completed)
        wrapped = asyncio.wrap_future(future, loop=loop)
        wrapped.add_done_callback(lambda f: None if f.cancelled() else f.exception())
        try:
            return await asyncio.shield(wrapped)
        except asyncio.CancelledError:
            with lock:
                state['abandoned'] = True
            raise

    def close(self):
        self.closed = True
        if self.loop is not None and not self.loop.is_closed():
            def stop_waiters():
                for waiter in tuple(self.waiters):
                    waiter.cancel()
            self.loop.call_soon_threadsafe(stop_waiters)

    def snapshot(self):
        return dict(capacity=self.capacity, inflight=self.inflight,
                    waiting=len(self.waiters), maximum=self.maximum,
                    completed=self.completed, closed=self.closed)
