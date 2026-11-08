"""Independent native potion work for a loaded solo actor; scene changes drain it."""
import asyncio,time,sqlite3
from contextlib import closing
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from els_server.business_queue import BoundedBusinessQueue


# These producers do not select a character, enter/leave a room or advance
# the scene. All other input is an ordering barrier for independent medicine.
COMBAT_KINDS=frozenset((0xad,0xd0,0x640,0x3e6,0x38e,0xff20,0xff21,0x7d0))


def combat(event):
    return event.event_id==0x202 and event.kind in COMBAT_KINDS


def selected(s):
    from els_server.domain.equipment_chip_flow import current_lease
    app=s.application;world=app.world;run=s.dungeon_run
    return (s.role=='game'and s.client_build=='dx11_260923'and s.item_test
        and s.phase=='dungeon_active'and s.dungeon_substage_synced
        and run is not None and run.encounter is None
        and not s.clear_notified and not s.dungeon_failed and not s.gate_stage_loading
        and not s.released and not s.coop_error and not s.social_overflow
        and getattr(s,'challenge_deadline',None)is None
        and getattr(s,'active_challenge',None)is None
        and world.party_of.get(s)is None and world.dungeons.room(s)is None
        and world.pvp.room(s)is None and world.racing.room(s)is None
        and world.field_bosses.room(s)is None and current_lease(s))


def epoch(s):
    r=s.dungeon_run
    return (s.account,s.account.store,s.account.uid,s.account.account_id,
        s.shop_session_id,r,r.run_id,r.stage,r.part,r.visits,s.reward_run_id)


class ConsumableWorkers:
    def __init__(self):
        self.executor=ThreadPoolExecutor(max_workers=4,thread_name_prefix='els-consumable')
        self.queue=BoundedBusinessQueue(self.executor,capacity=16)

    async def level(self,binding):
        path=binding[1].path;uid=binding[2];account=binding[3]
        def read():
            with closing(sqlite3.connect(Path(path).as_uri()+'?mode=ro',uri=True,timeout=10))as db:
                row=db.execute('SELECT c.level FROM characters c JOIN character_owners o ON o.uid=c.uid WHERE c.uid=? AND o.account_id=?',(uid,account)).fetchone()
                return row[0]if row else None
        return await self.queue.run(read)

    async def run(self,s,request,binding):
        def authorize(db):
            if (not selected(s)or epoch(s)!=binding
                    or not s.application.registry.enabled(binding[3])):
                raise ValueError('Consumable actor or loaded scene changed')
        def use():
            from els_server.domain.consumable_flow import handle
            return handle(s,request.event,request.sequence,authorize=authorize)
        return await self.queue.run(use)

    def close(self):
        self.queue.close();self.executor.shutdown(wait=True,cancel_futures=True)


class ConsumableLane:
    def __init__(self,application,session,scheduler,send,log,failure):
        self.application=application;self.session=session;self.scheduler=scheduler
        self.send=send;self.log=log;self.failure=failure
        self.requests=asyncio.Queue(8);self.task=None;self.closed=False
        self.pending=0
        self.serial_pending=0;self.idle=asyncio.Event();self.idle.set()
        self.error=None

    async def admit(self,request,inbox):
        s=self.session
        if (self.closed or request.event.event_id!=0x202
                or request.event.kind not in(0x113,0x65e)
                or len(request.event.payload)!=5 or len(request.event.performers)>1
                or not selected(s)):
            return False
        # A selected/running upkeep owns the actor until its original reply
        # is written. Do not overlap it or overtake any earlier scene input.
        slot=next((v for v in self.scheduler.slots.values()if v.session is s),None)
        if inbox.current is not None and not combat(inbox.current.event):return False
        if any(not combat(r.event)for r in inbox.pending):return False
        binding=epoch(s);accepted=False;serialized=True
        previous_done=inbox.current_done
        self.pending+=1;self.serial_pending+=1;self.idle.clear();s._consumable_pending=self.pending
        try:
            level=await self.application.consumables.level(binding)
            if level is None:return False
            if level==99:
                self.serial_pending-=1;serialized=False
            elif previous_done is not None:
                # A below-cap death may emit a level/full-unit update. Let
                # that single current reply finish before healing, then keep
                # subsequent deaths behind this potion until its effect sends.
                await asyncio.shield(previous_done)
            if slot is not None:
                claim=slot.claim;finished=slot.finished
                if claim is not None and claim.state=='running':
                    # Let the already-started atomic upkeep retire, then keep
                    # this potion ahead of queued combat rather than returning
                    # it to the ordinary FIFO behind the entire burst.
                    await asyncio.shield(finished)
                else:
                    await self.scheduler._cancel_waiter(slot)
                    claim=slot.claim
                    if claim is not None:
                        if claim.cancel():
                            slot.operation.release();self.scheduler.metrics['preempted']+=1
                        else:await asyncio.shield(slot.finished)
            if (self.closed or not selected(s)or epoch(s)!=binding
                    or inbox.current is not None and not combat(inbox.current.event)
                    or any(not combat(r.event)for r in inbox.pending)):
                return False
            self.requests.put_nowait((request,binding,serialized));accepted=True
        finally:
            if not accepted:
                if serialized:self.serial_pending-=1
                self.pending-=1;s._consumable_pending=self.pending;self.scheduler.wake.set()
                if not self.pending:self.idle.set()
        self.log('client_request',sequence=request.sequence,event_id=request.event.event_id,
            kind=request.event.kind,size=request.size,lane='consumable')
        if self.task is None:
            self.task=asyncio.create_task(self._run(),name='native-consumable')
            self.task.add_done_callback(lambda task:None if task.cancelled()else task.exception())
        return True

    async def _run(self):
        try:
            while not self.requests.empty():
                request,binding,serialized=self.requests.get_nowait();started=time.perf_counter()
                try:
                    messages=await self.application.consumables.run(self.session,request,binding)
                    timing=dict(connection_wait_ms=(started-request.received)*1000,encode_ms=0.,send_ms=0.)
                    # This source-free ACK/effect must not consume another
                    # worker's pending native attribute/skill source receipt.
                    await self.send(messages,send_path='consumable',request_sequence=request.sequence,
                        request_kind=request.event.kind,timing=timing)
                    self.log('request_timing',sequence=request.sequence,kind=request.event.kind,
                        phase=self.session.phase,calls=[dict(lane='consumable')],reply_complete=True,
                        total_ms=(time.perf_counter()-request.received)*1000,**timing)
                finally:
                    if serialized:self.serial_pending-=1
                    self.pending-=1;self.session._consumable_pending=self.pending
                    if not self.pending:self.idle.set()
                    self.requests.task_done();self.scheduler.wake.set()
        except Exception as error:
            self.closed=True;self.error=error
            self.failure(error)
            while not self.requests.empty():
                _,_,serialized=self.requests.get_nowait();self.requests.task_done();self.pending-=1
                if serialized:self.serial_pending-=1
            self.session._consumable_pending=self.pending
            if not self.pending:self.idle.set()
            raise
        finally:self.task=None

    async def drain(self):
        await self.idle.wait()
        if self.error is not None:raise self.error

    async def close(self):
        self.closed=True
        task=self.task;cancelled=False
        if task is not None:
            while not task.done():
                try:await asyncio.shield(task)
                except asyncio.CancelledError:cancelled=True
            task.result()
        if cancelled:raise asyncio.CancelledError
        if self.error is not None:raise self.error
