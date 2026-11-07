"""Bounded FIFO lanes share byte quanta, preserving each connection's order."""
import asyncio,time
from collections import deque
from dataclasses import dataclass

@dataclass(eq=False)
class _Waiter:
    size:int
    future:object
    transient:bool=False
    queued:bool=True

class EgressBudget:
    chunk_size=1024
    def __init__(self,mbps,max_waiters):
        self.rate=mbps*125000;self.capacity=16384;self.tokens=float(self.capacity)
        self.updated=time.monotonic();self.max_waiters=max_waiters
        self.waiters=deque();self.town_waiters=deque();self.town_turn=False;self.served_bytes=0
        self.wake=asyncio.Event();self.task=None;self.closed=False

    def _refill(self):
        now=time.monotonic()
        self.tokens=min(self.capacity,self.tokens+(now-self.updated)*self.rate);self.updated=now

    async def wait(self,size,*,transient=False):
        if self.closed:raise ConnectionError('Egress budget is closed')
        if not 0<size<=self.chunk_size:raise ValueError('Egress chunk size')
        self._refill()
        if not self.waiters and not self.town_waiters and self.tokens>=size:self.tokens-=size;return
        if len(self.waiters)+len(self.town_waiters)>=self.max_waiters:raise BufferError('Egress waiter limit')
        queue=self.town_waiters if transient else self.waiters
        waiter=_Waiter(size,asyncio.get_running_loop().create_future(),transient);queue.append(waiter)
        self.wake.set()
        if self.task is None:self.task=asyncio.create_task(self._run(),name='shared-egress-budget')
        try:await waiter.future
        finally:
            if waiter.queued:
                queue.remove(waiter);waiter.queued=False;self.wake.set()

    def _queue(self):
        current,other=(self.town_waiters,self.waiters)if self.town_turn else(self.waiters,self.town_waiters)
        if other and(not current or self.served_bytes>=self.chunk_size):
            self.town_turn=not self.town_turn;self.served_bytes=0
            return other
        return current

    async def _run(self):
        try:
            while self.waiters or self.town_waiters:
                self.wake.clear();self._refill()
                while self.waiters or self.town_waiters:
                    queue=self._queue();waiter=queue[0]
                    if waiter.future.done():queue.popleft();waiter.queued=False;continue
                    if self.tokens<waiter.size:break
                    queue.popleft();waiter.queued=False;self.tokens-=waiter.size
                    self.served_bytes+=waiter.size
                    waiter.future.set_result(None)
                if not self.waiters and not self.town_waiters:break
                delay=(self._queue()[0].size-self.tokens)/self.rate
                try:await asyncio.wait_for(self.wake.wait(),delay)
                except TimeoutError:pass
        except BaseException as error:
            for waiter in (*self.waiters,*self.town_waiters):
                waiter.queued=False
                if not waiter.future.done():waiter.future.set_exception(error)
            self.waiters.clear();self.town_waiters.clear();raise
        finally:self.task=None

    def refund(self,size):
        self._refill();self.tokens=min(self.capacity,self.tokens+size);self.wake.set()

    async def close(self):
        self.closed=True
        for waiter in (*self.waiters,*self.town_waiters):
            waiter.queued=False
            if not waiter.future.done():waiter.future.set_exception(ConnectionError('Egress budget closed'))
        self.waiters.clear();self.town_waiters.clear();self.wake.set()
        if self.task is not None:await self.task
