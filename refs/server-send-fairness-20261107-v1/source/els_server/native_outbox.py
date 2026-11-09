"""Bounded connection order; only source-free town positions may be replaced."""
import asyncio,time
from collections import deque
from dataclasses import dataclass,field

def town_messages(messages):
    return bool(messages)and all(e.event_id==0x201 and e.kind in(0x22a,0x22e)for e in messages)

def wire_size(event):
    plaintext=30+8*len(event.performers)+len(event.payload)+bool(event.payload)
    return 32+(plaintext//8+1)*8

@dataclass
class TownBatch:
    messages:tuple=()
    positions:dict=field(default_factory=dict)
    size:int=0

    def merged(self,messages):
        values=list(self.messages);positions=dict(self.positions);size=self.size;replaced=0
        for event in messages:
            cost=len(event.payload)+128
            if event.kind==0x22e:
                uid=event.payload[:8]
                if uid in positions:
                    index=positions[uid];size-=len(values[index].payload)+128
                    values[index]=event;replaced+=1
                else:positions[uid]=len(values);values.append(event)
            else:
                values.append(event);positions.clear()
            size+=cost
        if len(values)>256 or size>256*1024:raise BufferError('Town outbound batch limit')
        return TownBatch(tuple(values),positions,size),replaced

@dataclass
class _Group:
    messages:tuple
    options:dict
    deadline:float
    future:object
    context:object=None
    town:object=None
    size:int=0

class NativeOutbox:
    byte_limit=2*1024*1024
    group_limit=8
    def __init__(self,send,budget,timeout,failure,metrics):
        self.send=send;self.budget=budget;self.timeout=timeout;self.failure=failure;self.metrics=metrics
        self.groups=deque();self.task=None;self.bytes=0;self.closed=False;self.error=None
        for key in ('outbound_pending_bytes','outbound_peak_bytes','outbound_queued_town','outbound_coalesced_positions','outbound_batches','outbound_queue_max_ms'):
            metrics.setdefault(key,0)

    def _charge(self,delta):
        self.bytes+=delta;self.metrics['outbound_pending_bytes']+=delta
        self.metrics['outbound_peak_bytes']=max(self.metrics['outbound_peak_bytes'],self.metrics['outbound_pending_bytes'])

    async def submit(self,messages,options,*,transient=False,context=None):
        if self.error is not None:raise self.error
        if self.closed:raise ConnectionError('Native outbox closed')
        messages=tuple(messages);tail=self.groups[-1]if self.groups else None
        if transient and tail is not None and tail.town is not None and tail.context==context:
            batch,replaced=tail.town.merged(messages);delta=batch.size-tail.size
            if self.bytes+delta>self.byte_limit:raise BufferError('Native outbound byte limit')
            tail.town=batch;tail.size=batch.size;self._charge(delta)
            self.metrics['outbound_coalesced_positions']+=replaced;return False
        size=sum(len(e.payload)+128 for e in messages)
        if len(self.groups)>=self.group_limit or self.bytes+size>self.byte_limit:raise BufferError('Native outbound queue limit')
        future=None if transient else asyncio.get_running_loop().create_future()
        group=_Group(messages,dict(options),time.monotonic()+self.timeout,future,context,size=size)
        if transient:
            group.town,_=TownBatch().merged(messages);group.size=group.town.size
            group.messages=()
            # Town receipt-free events carry no own native source observation.
            group.options.update(send_path='realtime',timing=None)
            self.metrics['outbound_queued_town']+=1
        self.groups.append(group);self._charge(group.size)
        if self.task is None:self.task=asyncio.create_task(self._run(),name='native-outbound')
        if transient:return False
        await future;return True

    async def _run(self):
        active=None
        try:
            while self.groups:
                group=self.groups[0];credit=0
                async with asyncio.timeout_at(group.deadline):
                    if group.town is not None and self.budget is not None:
                        # Keep DTOs mutable/coalescible until bandwidth is ready.
                        credit=min(self.budget.chunk_size,sum(wire_size(e)for e in group.town.messages))
                        await self.budget.wait(credit,transient=all(e.kind==0x22e for e in group.town.messages))
                    self.groups.popleft();active=group
                    self.metrics['outbound_queue_max_ms']=max(self.metrics['outbound_queue_max_ms'],(time.monotonic()-(group.deadline-self.timeout))*1000)
                    messages=group.town.messages if group.town is not None else group.messages
                    await self.send(messages,credit=credit,**group.options)
                    self.metrics['outbound_batches']+=1
                    if group.future is not None and not group.future.done():group.future.set_result(None)
                self._charge(-group.size);active=None
        except BaseException as error:
            if active is not None:
                self._charge(-active.size)
                if active.future is not None and not active.future.done():active.future.set_exception(error)
            while self.groups:
                group=self.groups.popleft();self._charge(-group.size)
                if group.future is not None and not group.future.done():group.future.set_exception(error)
            if not isinstance(error,asyncio.CancelledError):
                self.error=error;self.failure(error)
        finally:self.task=None

    async def close(self):
        self.closed=True
        if self.task is not None:
            self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)
        self.send=None;self.failure=None;self.error=None
