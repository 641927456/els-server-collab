"""Two pure preparation workers; no unbounded executor backlog or session access."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
import time


class PreparationBusy(ValueError):pass


class BoundedPreparation:
    def __init__(self):
        self.executor=ThreadPoolExecutor(max_workers=2,thread_name_prefix='els-prepare')
        self.lock=threading.Lock();self.active=0;self.closed=False
        self.metrics=dict(accepted=0,rejected=0,completed=0,max_ms=0.)

    async def run(self,function,*args):
        # Capacity stays occupied until real work finishes, even if a caller
        # disconnects. Never release it just because an await was cancelled.
        with self.lock:
            if self.closed or self.active>=2:
                self.metrics['rejected']+=1
                raise PreparationBusy('rate_limited')
            self.active+=1;self.metrics['accepted']+=1
        started=time.perf_counter()
        try:future=self.executor.submit(function,*args)
        except BaseException:
            with self.lock:self.active-=1
            raise
        def done(_):
            with self.lock:
                self.active-=1;self.metrics['completed']+=1
                self.metrics['max_ms']=max(self.metrics['max_ms'],(time.perf_counter()-started)*1000)
        future.add_done_callback(done)
        wrapped=asyncio.wrap_future(future)
        # Retrieve detached errors, without logging credential-bearing inputs.
        wrapped.add_done_callback(lambda f: None if f.cancelled() else f.exception())
        return await asyncio.shield(wrapped)

    def snapshot(self):
        with self.lock:return dict(self.metrics,active=self.active,capacity=2)

    def close(self):
        with self.lock:self.closed=True
        self.executor.shutdown(wait=True,cancel_futures=True)
