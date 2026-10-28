"""Bounded, coalesced attribute arithmetic outside the account executor.

All scheduling methods belong to one asyncio loop. A build owns no business
session and returns an immutable value plus its read-only source lease. The
caller must take and encode under its existing session operation lock, after
ordinary replies/55B and Actor identity restoration, without an intervening
business mutation. This module does not install a dispatcher or send packets.
"""
import asyncio
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Ticket:
    owner: int
    generation: int


@dataclass(frozen=True)
class Product:
    value: object
    lease: object
    valid_before: object


@dataclass
class _Entry:
    ticket: Ticket
    build: object
    product: object = None
    failure: object = None
    validation: object = None


class AttributeJobs:
    def __init__(self, *, capacity=32):
        if type(capacity) is not int or not 1 <= capacity <= 256:
            raise ValueError('Bounded native attribute job capacity required')
        self._loop = asyncio.get_running_loop()
        self._capacity = capacity
        self._entries = {}
        self._pending = OrderedDict()
        self._serial = 0
        self._closed = False
        self._pump = None
        self._closing = None
        self._validations = set()
        self._executor = ThreadPoolExecutor(max_workers=1,
                                            thread_name_prefix='els-attributes')

    def _check(self):
        if asyncio.get_running_loop() is not self._loop:
            raise RuntimeError('Native attribute job loop differs')

    @staticmethod
    def _close(entry):
        product, entry.product = entry.product, None
        if product is not None:
            product.lease.close()

    def refresh(self, key, owner, build):
        """Replace queued work for this session; never queue an unbounded future."""
        self._check()
        if self._closed:
            raise RuntimeError('Native attribute jobs closed')
        if type(owner) is not int or not 0 < owner < 2**64 or not callable(build):
            raise ValueError('Owned native attribute build required')
        old = self._entries.get(key)
        if old is None and len(self._entries) >= self._capacity:
            raise OverflowError('Native attribute job capacity reached')
        if old is not None:
            self._close(old)
        self._serial += 1
        ticket = Ticket(owner, self._serial)
        entry = _Entry(ticket, build)
        self._entries[key] = entry
        # Assignment retains another session's earlier queue position.
        self._pending[key] = entry
        if self._pump is None or self._pump.done():
            self._pump = self._loop.create_task(self._run(), name='native-attribute-jobs')
        return ticket

    def discard(self, key):
        self._check()
        self._pending.pop(key, None)
        entry = self._entries.pop(key, None)
        if entry is not None:
            self._close(entry)

    async def _run(self):
        while self._pending and not self._closed:
            key, entry = self._pending.popitem(last=False)
            work = self._executor.submit(entry.build)
            future = asyncio.wrap_future(work, loop=self._loop)
            try:
                product = await asyncio.shield(future)
                if type(product) is not Product:
                    raise ValueError('Complete native attribute product required')
                entry.product = product
                if self._entries.get(key) is not entry or self._closed:
                    self._close(entry)
            except asyncio.CancelledError:
                # A cancelled asyncio waiter cannot cancel an already running
                # native calculation. Its eventual lease still needs an owner.
                def dispose(completed):
                    try:
                        result = completed.result()
                        if type(result) is Product:
                            result.lease.close()
                    except Exception:
                        pass  # Source failure is already represented below.
                work.add_done_callback(dispose)
                future.add_done_callback(lambda f: None if f.cancelled() else f.exception())
                entry.failure = RuntimeError('Native attribute worker cancelled')
                raise
            except Exception as error:
                entry.failure = error
            finally:
                # Do not retain a build closure and its entire source snapshot.
                entry.build = None

    def take(self, key, ticket, *, at):
        """Consume once; stale/expired generations return None and release leases.

        None requires a fresh scheduled capture, not a zero-valued notification.
        Build failures remain visible to the caller instead of being reported as
        successful refreshes. A wrong ticket cannot consume the latest result.
        """
        self._check()
        if type(ticket) is not Ticket:
            raise ValueError('Native attribute ticket required')
        if type(at) not in (int, float) or not math.isfinite(at):
            raise ValueError('Native attribute validation time required')
        entry = self._entries.get(key)
        if entry is None or entry.ticket != ticket:
            return None
        if entry.failure is not None:
            self.discard(key)
            raise entry.failure
        product = entry.product
        if product is None:
            return None
        try:
            end = product.valid_before
            if end is not None and (type(end) not in (int, float)
                                    or not math.isfinite(end) or at >= end):
                return None
            if not product.lease.current():
                return None
            return product.value
        finally:
            self.discard(key)

    async def revalidate(self, key, ticket, *, at):
        """Coalesce source-only checks on the owned worker before final take.

        Call outside the session operation lock, then reacquire that lock and
        recheck Actor/session identity and use take with a fresh clock. Awaiting
        this method never consumes a product or sends a packet. A stale ticket,
        expiry, concurrent logout or source change cannot revive a generation.
        """
        self._check()
        if type(ticket) is not Ticket:
            raise ValueError('Native attribute ticket required')
        if type(at) not in (int, float) or not math.isfinite(at):
            raise ValueError('Native attribute validation time required')
        entry = self._entries.get(key)
        if self._closed or entry is None or entry.ticket != ticket or entry.product is None:
            return False
        product = entry.product
        end = product.valid_before
        if end is not None and (type(end) not in (int, float) or not math.isfinite(end) or at >= end):
            return False
        if entry.validation is None:
            async def validate():
                return await self._loop.run_in_executor(
                    self._executor, lambda: product.lease.revalidate(at=at))
            entry.validation = self._loop.create_task(validate(), name='native-attribute-source-check')
            self._validations.add(entry.validation)
            def finished(task):
                self._validations.discard(task)
                if not task.cancelled():
                    task.exception()  # Observe failure even if every waiter was cancelled.
            entry.validation.add_done_callback(finished)
        validation = entry.validation
        try:
            valid = await asyncio.shield(validation)
            return bool(valid and self._entries.get(key) is entry and entry.product is product
                        and not self._closed)
        finally:
            if entry.validation is validation and validation.done():
                entry.validation = None

    async def close(self):
        self._check()
        if self._closing is None:
            self._closed = True
            for key in tuple(self._entries):
                self.discard(key)
            self._closing = self._loop.create_task(self._finish_close())
        await asyncio.shield(self._closing)

    async def _finish_close(self):
        try:
            if self._pump is not None:
                try:
                    await asyncio.shield(self._pump)
                except asyncio.CancelledError:
                    if not self._pump.cancelled():
                        raise
        finally:
            # Join off-loop; returning from close means no owned worker remains.
            await asyncio.to_thread(self._executor.shutdown, wait=True, cancel_futures=True)
            if self._validations:
                await asyncio.gather(*tuple(self._validations), return_exceptions=True)
