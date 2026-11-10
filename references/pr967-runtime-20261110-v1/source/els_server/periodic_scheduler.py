"""Deadline-driven bounded batches, retaining per-connection reply ownership."""
import asyncio
import time
from collections import deque
from types import SimpleNamespace


class PeriodicScheduler:
    def __init__(self,application,interval,log):
        self.application=application;self.interval=interval;self.log=log
        self.slots={};self.task=None;self.wake=asyncio.Event();self.closing=False
        self.deliveries=set()
        self.metrics=dict(batches=0,members=0,max_batch=0,busy_skips=0,slices=0,max_slice=0,dispatch_late_max_ms=0.)
        self.dispatch_lateness=deque(maxlen=256)

    def snapshot(self):
        result=dict(self.metrics)
        values=sorted(self.dispatch_lateness)
        result['dispatch_late_window_count']=len(values)
        result['dispatch_late_ms_p95']=round(values[(95*len(values)+99)//100-1],3) if values else 0.
        return result

    async def serve(self,session,operation,send):
        if self.closing:raise RuntimeError('Periodic scheduler closed')
        loop=asyncio.get_running_loop()
        slot=SimpleNamespace(session=session,operation=operation,send=send,
            due=time.monotonic()+self.interval,closed=False,finished=None,failure=loop.create_future())
        key=id(slot);self.slots[key]=slot;self.wake.set()
        if self.task is None:self.task=asyncio.create_task(self._run(),name='periodic-batches')
        try:await slot.failure
        finally:
            slot.closed=True;self.slots.pop(key,None);self.wake.set()
            if slot.finished is not None:await asyncio.shield(slot.finished)

    async def _deliver(self,slot,messages,error):
        try:
            if error is not None:raise error
            if not slot.closed:await slot.send(messages)
        except Exception as error:
            if not slot.failure.done():slot.failure.set_exception(error)
        finally:
            slot.due=time.monotonic()+self.interval
            slot.operation.release()
            slot.finished.set_result(None);slot.finished=None
            self.wake.set()

    async def _run(self):
        try:
            while not self.closing:
                self.wake.clear();now=time.monotonic();ready=[]
                for slot in sorted(self.slots.values(), key=lambda value: value.due):
                    if slot.closed or slot.finished is not None or slot.due>now:continue
                    if slot.operation.locked():
                        self.metrics['busy_skips']+=1;continue
                    # acquire() on an unlocked asyncio.Lock does not suspend.
                    await slot.operation.acquire()
                    # Selection delay only: worker admission/batch delay is
                    # recorded separately; this is not a delivery or RTT claim.
                    late=max(0.,(time.monotonic()-slot.due)*1000)
                    self.dispatch_lateness.append(late)
                    self.metrics['dispatch_late_max_ms']=max(self.metrics['dispatch_late_max_ms'],late)
                    slot.finished=asyncio.get_running_loop().create_future();ready.append(slot)
                    if len(ready)==16:break
                if ready:
                    self.metrics['batches']+=1;self.metrics['members']+=len(ready)
                    self.metrics['max_batch']=max(self.metrics['max_batch'],len(ready))
                    completed=0
                    def deliver(results):
                        nonlocal completed
                        if not results or completed+len(results)>len(ready):
                            raise RuntimeError('Periodic result bounds')
                        for messages,error in results:
                            slot=ready[completed];completed+=1
                            task=asyncio.create_task(self._deliver(slot,messages,error))
                            self.deliveries.add(task);task.add_done_callback(self.deliveries.discard)
                        self.metrics['slices']+=1
                        self.metrics['max_slice']=max(self.metrics['max_slice'],len(results))
                    try:
                        chunks=getattr(self.application,'periodic_chunks',None)
                        sessions=tuple(s.session for s in ready)
                        if chunks is None:
                            deliver(await self.application.periodic_batch(sessions))
                        else:
                            async for results in chunks(sessions):deliver(results)
                        if completed!=len(ready):raise RuntimeError('Incomplete periodic results')
                    except Exception as error:
                        # Completed members already own their delivery tasks. A
                        # later admission failure must not send or unlock twice.
                        if completed<len(ready):deliver([(None,error)]*(len(ready)-completed))
                    summary=self.application.performance.due()
                    if summary is not None:
                        queue=getattr(self.application,'business_queue',None)
                        cache=getattr(self.application,'accounts',None)
                        cache_metrics={'account_cache':cache.snapshot()} if callable(getattr(cache,'snapshot',None)) else {}
                        self.log('application_timing_summary',operations=summary,periodic=self.snapshot(),
                            requests=self.application.performance.request_snapshot(),
                            business_queue=queue.snapshot() if queue is not None else {},
                            preparation=self.application.preparation.snapshot(),**cache_metrics)
                    continue
                # A busy socket or in-flight send never causes a zero-delay
                # spin. New members and completed sends wake the deadline wait.
                due=[s.due for s in self.slots.values() if not s.closed and s.finished is None and not s.operation.locked()]
                delay=max(.001,min(self.interval,min(due)-time.monotonic())) if due else self.interval
                try:await asyncio.wait_for(self.wake.wait(),delay)
                except TimeoutError:pass
        except Exception as error:
            for slot in list(self.slots.values()):
                if not slot.failure.done():slot.failure.set_exception(error)
            raise

    async def close(self):
        self.closing=True;self.wake.set()
        if self.task is not None:await self.task
        if self.deliveries:await asyncio.gather(*self.deliveries,return_exceptions=True)
