"""Deadline-driven bounded batches, retaining per-connection reply ownership."""
import asyncio
import time
from collections import deque
from types import SimpleNamespace
from contextlib import asynccontextmanager
from els_server.periodic_work import PeriodicClaim


def _town_notice_pending(session):
    mailbox=getattr(session,'mailbox',None)
    return (getattr(session,'role',None)=='game'and getattr(session,'phase',None)=='town_ready'
        and mailbox is not None and bool(mailbox.messages))


class PeriodicScheduler:
    def __init__(self,application,interval,log):
        self.application=application;self.interval=interval;self.log=log
        self.loop=None;application.periodic_notify=self.notify
        self.slots={};self.task=None;self.wake=asyncio.Event();self.closing=False
        self.deliveries=set();self.polls=set()
        application.dungeon_workers.upkeep_available=self.wake.set
        self.metrics=dict(batches=0,members=0,max_batch=0,busy_skips=0,slices=0,max_slice=0,dispatch_late_max_ms=0.,preempted=0,cooperative_yields=0,completed_polls=0)
        self.dispatch_lateness=deque(maxlen=256)

    def notify(self,session):
        if self.loop is not None and not self.closing:self.loop.call_soon_threadsafe(self._notify,session)

    def _notify(self,session):
        for slot in self.slots.values():
            if slot.session is session:
                slot.wake_generation+=1
                now=time.monotonic()
                queued_town_notice=_town_notice_pending(session)
                slot.due=min(slot.due,now if queued_town_notice else max(now,slot.last_completed+self.interval))
                self.wake.set();break

    def snapshot(self):
        result=dict(self.metrics)
        values=sorted(self.dispatch_lateness)
        result['dispatch_late_window_count']=len(values)
        result['dispatch_late_ms_p95']=round(values[(95*len(values)+99)//100-1],3) if values else 0.
        return result

    async def serve(self,session,operation,send):
        if self.closing:raise RuntimeError('Periodic scheduler closed')
        loop=asyncio.get_running_loop()
        self.loop=loop
        slot=SimpleNamespace(session=session,operation=operation,send=send,
            due=time.monotonic()+self.interval,closed=False,finished=None,waiting=None,
            claim=None,upkeep_reserved=False,foreground=False,foreground_completed=float("-inf"),last_completed=time.monotonic(),wake_generation=0,poll_generation=0,failure=loop.create_future())
        key=id(slot);self.slots[key]=slot;self.wake.set()
        if self.task is None:self.task=asyncio.create_task(self._run(),name='periodic-batches')
        try:await slot.failure
        finally:
            slot.closed=True;self.slots.pop(key,None);self.wake.set()
            await self._cancel_waiter(slot)
            if slot.finished is not None:await asyncio.shield(slot.finished)
            # Loop locals can retain retired slots. Failed Futures also hold
            # serve's traceback and actor, independently of the sender closure.
            slot.send=None;slot.session=None;slot.failure=None

    async def _cancel_waiter(self,slot):
        waiter,slot.waiting=slot.waiting,None
        if waiter is None:return
        waiter.cancel()
        try:await waiter
        except asyncio.CancelledError:pass
        else:slot.operation.release()
        if slot.upkeep_reserved:
            semaphore,slot.upkeep_reserved=slot.upkeep_reserved,False
            self.application.dungeon_workers.release_upkeep(semaphore)

    @asynccontextmanager
    async def foreground(self,session,operation):
        slot=next((s for s in self.slots.values()if s.session is session),None)
        phase_before=None
        if slot is not None:slot.foreground=True
        try:
            # Only a poll with real execution capacity can reserve an old
            # foreground place. Waiting for a background world-reader turn
            # must not retain the player's operation through scene admission.
            # Started work always keeps its original retirement ownership.
            if slot is not None and(slot.claim is None or not slot.claim.admitted
                    or time.monotonic()-slot.last_completed<1):
                await self._cancel_waiter(slot)
                if slot.claim is not None and slot.claim.cancel():
                    slot.operation.release();self.metrics['preempted']+=1
            async with operation:
                phase_before=getattr(session,'phase',None)
                yield
        finally:
            if slot is not None:
                if phase_before is not None and getattr(session,'phase',None)!=phase_before:
                    slot.last_completed=time.monotonic()
                slot.foreground_completed=time.monotonic()
                slot.foreground=False;slot.due=min(slot.due,getattr(session,'_periodic_due',time.monotonic()+self.interval));self.wake.set()

    async def _deliver(self,slot,messages,error):
        claim=slot.claim
        try:
            if claim.cancelled:return
            if error is not None:raise error
            if not slot.closed:await slot.send(messages)
        except Exception as error:
            if not slot.closed and not slot.failure.done():slot.failure.set_exception(error)
        finally:
            pending=getattr(slot.session,'_periodic_pending',False)
            now=time.monotonic()
            queued_town_notice=(slot.wake_generation!=slot.poll_generation and _town_notice_pending(slot.session))
            slot.due=(now if pending or queued_town_notice else now+self.interval if slot.wake_generation!=slot.poll_generation
                else max(now,getattr(slot.session,'_periodic_due',now+self.interval)))
            if not claim.cancelled:
                slot.last_completed=time.monotonic()
                if pending:self.metrics['cooperative_yields']+=1
                else:
                    self.metrics['completed_polls']+=1
                slot.operation.release()
            slot.claim=None
            slot.finished.set_result(None);slot.finished=None
            self.wake.set()

    async def _poll(self,ready):
        # Each dungeon domain owns its own poll and reply delivery. A slow
        # room must not retain another room's per-connection operation lock.
        completed=0
        claims=tuple(s.claim for s in ready)
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
                for slot in ready:slot.claim.start()
                deliver(await self.application.periodic_batch(sessions))
            else:
                async for results in chunks(sessions,claims=tuple(s.claim for s in ready)):deliver(results)
            if completed!=len(ready):raise RuntimeError('Incomplete periodic results')
            summary=self.application.performance.due()
            if summary is not None:
                queue=getattr(self.application,'business_queue',None)
                cache=getattr(self.application,'accounts',None)
                cache_metrics={'account_cache':cache.snapshot()} if callable(getattr(cache,'snapshot',None)) else {}
                self.log('application_timing_summary',operations=summary,periodic=self.snapshot(),
                    requests=self.application.performance.request_snapshot(),
                    business_queue=queue.snapshot() if queue is not None else {},
                    preparation=self.application.preparation.snapshot(),economy=self.application.economy.snapshot(),dungeon_workers=self.application.dungeon_workers.snapshot(),coin_writer=self.application.coin_writer.snapshot(),**cache_metrics)
        except Exception as error:
            if completed<len(ready):deliver([(None,error)]*(len(ready)-completed))
            else:
                for slot in ready:
                    if not slot.closed and not slot.failure.done():slot.failure.set_exception(error)
        finally:
            # A foreground request may cancel a selected claim and change its
            # scene before dispatch. Return any reserved lane it did not use.
            for claim in claims:
                if claim.upkeep_reserved:
                    semaphore,claim.upkeep_reserved=claim.upkeep_reserved,False
                    self.application.dungeon_workers.release_upkeep(semaphore)

    async def _run(self):
        ready=[]
        try:
            while not self.closing:
                self.wake.clear();now=time.monotonic();ready=[];capacity_blocked=set();followup_deadlines={}
                for slot in sorted(self.slots.values(), key=lambda value: value.due):
                    if slot.closed or slot.finished is not None or slot.due>now:continue
                    if getattr(slot.session,'_consumable_pending',0):continue
                    if slot.foreground and slot.waiting is None and now-slot.last_completed<1:continue
                    if (not slot.foreground and slot.waiting is None
                            and slot.wake_generation==slot.poll_generation and now-slot.last_completed<1):
                        # Native reply-followups arrive before the next regular
                        # poll interval. Leave a fresh quiet upkeep turn behind
                        # them; notifications, old polls and reserved turns keep
                        # their original admission and retirement ownership.
                        followup=min(slot.foreground_completed+self.interval,slot.last_completed+1)
                        # Keep the real due unchanged so a new notification
                        # can still wake its original immediate turn.
                        if now<followup:
                            followup_deadlines[id(slot)]=followup;continue
                    if slot.waiting is None:
                        workers=self.application.dungeon_workers
                        upkeep=(workers.candidate(slot.session.periodic_notifications,())
                            and not workers.town_mailbox(slot.session.periodic_notifications,()))
                        if upkeep:
                            # Do not join connection FIFOs while workers are
                            # saturated. Recheck capacity after that turn;
                            # waiting for an actor never reserves a worker.
                            semaphore=workers.upkeep_admission_for(slot.session)
                            if semaphore.locked():
                                capacity_blocked.add(id(slot));continue
                        # Join the lock's FIFO once without blocking other slots.
                        # Even an unlocked lock can have a woken request waiter.
                        if slot.operation.locked():self.metrics['busy_skips']+=1
                        slot.waiting=asyncio.create_task(slot.operation.acquire())
                        slot.waiting.add_done_callback(lambda task:self.wake.set())
                        continue
                    if not slot.waiting.done():continue
                    # The completed waiter still owns this operation until a
                    # claim takes over. Classification can fail in between.
                    slot.waiting.result()
                    workers=self.application.dungeon_workers
                    upkeep=(workers.candidate(slot.session.periodic_notifications,())
                        and not workers.town_mailbox(slot.session.periodic_notifications,()))
                    if upkeep:
                        # A busy actor has no worker yet. Reserve the lane
                        # only after its FIFO connection turn is acquired;
                        # never retain that turn waiting for another actor.
                        semaphore=workers.upkeep_admission_for(slot.session)
                        if semaphore.locked():
                            slot.waiting=None;slot.operation.release();capacity_blocked.add(id(slot));continue
                        await semaphore.acquire();slot.upkeep_reserved=semaphore
                    # Selection delay only: worker admission/batch delay is
                    # recorded separately; this is not a delivery or RTT claim.
                    late=max(0.,(time.monotonic()-slot.due)*1000)
                    self.dispatch_lateness.append(late)
                    self.metrics['dispatch_late_max_ms']=max(self.metrics['dispatch_late_max_ms'],late)
                    slot.claim=PeriodicClaim()
                    slot.claim.upkeep_reserved=slot.upkeep_reserved;slot.upkeep_reserved=False
                    slot.poll_generation=slot.wake_generation
                    slot.finished=asyncio.get_running_loop().create_future();slot.waiting=None;ready.append(slot)
                    if len(ready)==16:break
                if ready:
                    self.metrics['batches']+=1;self.metrics['members']+=len(ready)
                    self.metrics['max_batch']=max(self.metrics['max_batch'],len(ready))
                    groups={};workers=self.application.dungeon_workers
                    for slot in ready:
                        key=workers.key(slot.session)if workers.candidate(slot.session.periodic_notifications,())else None
                        groups.setdefault(key,[]).append(slot)
                    for group in groups.values():
                        task=asyncio.create_task(self._poll(group))
                        self.polls.add(task);task.add_done_callback(self.polls.discard)
                        for slot in group:ready.remove(slot)
                    continue
                # A busy socket or in-flight send never causes a zero-delay
                # spin. New members and completed sends wake the deadline wait.
                # Worker retirement/delivery already wakes this scheduler.
                # An overdue actor without a free upkeep lane cannot provide
                # a useful timer deadline: polling it every1ms just spins.
                due=[max(s.due,followup_deadlines.get(id(s),s.due)) for s in self.slots.values() if not s.closed and not s.foreground and s.finished is None and not s.operation.locked()and not getattr(s.session,'_consumable_pending',0)and id(s)not in capacity_blocked]
                delay=max(.001,min(due)-time.monotonic()) if due else self.interval
                try:await asyncio.wait_for(self.wake.wait(),delay)
                except TimeoutError:pass
        except Exception as error:
            # Selected claims which never reached a poll still own their
            # operation and capacity. Complete them through normal delivery.
            for slot in ready:
                claim=slot.claim
                if claim.upkeep_reserved:
                    semaphore,claim.upkeep_reserved=claim.upkeep_reserved,False
                    self.application.dungeon_workers.release_upkeep(semaphore)
                task=asyncio.create_task(self._deliver(slot,None,error))
                self.deliveries.add(task);task.add_done_callback(self.deliveries.discard)
            for slot in list(self.slots.values()):
                if not slot.closed and not slot.failure.done():slot.failure.set_exception(error)
            raise

    async def close(self):
        self.closing=True;self.wake.set()
        if self.application.dungeon_workers.upkeep_available==self.wake.set:self.application.dungeon_workers.upkeep_available=None
        if self.application.periodic_notify==self.notify:self.application.periodic_notify=None
        from els_server.cleanup import cleanup_all_async
        async def finish_polls():
            await cleanup_all_async(*(lambda task=task:task for task in tuple(self.polls)))
        async def finish_deliveries():
            if self.deliveries:await asyncio.gather(*self.deliveries,return_exceptions=True)
        # A failed dispatcher must not skip retirement of already running SQL
        # or replies. Keep the existing error after every lane has retired.
        await cleanup_all_async(lambda:self.task,
            *(lambda slot=slot:self._cancel_waiter(slot) for slot in list(self.slots.values())),
            finish_polls,finish_deliveries)
