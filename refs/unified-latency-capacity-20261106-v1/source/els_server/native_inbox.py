"""Bounded native input; coalesce only consecutive validated town positions."""
import asyncio
import time
from collections import deque
from dataclasses import dataclass
from els_server.protocol.protocol_codec import decode_frame,decode_event
from els_server.storage.local_state import movement_location,validate_location


@dataclass(frozen=True)
class Request:
    sequence:int
    event:object
    size:int
    received:float
    position:bool


def position(event):
    if not(event.event_id==0x202 and event.kind==0x22b and event.performers==(0,)
            and event.uid==event.target_uid==2**64-1 and event.payload_mode==0):return False
    try:
        board,progress,xyz=movement_location(event.payload,'dx11_260923')
        validate_location(20000,board,progress,xyz)
    except ValueError:return False
    return True


class NativeInbox:
    def __init__(self,read,keys,session,metrics,*,auxiliary=None):
        self.read=read;self.keys=keys;self.session=session;self.metrics=metrics
        self.pending=deque();self.bytes=0;self.condition=asyncio.Condition()
        self.error=None;self.moving=False
        self.auxiliary=auxiliary
        self.task=asyncio.create_task(self._read(),name='native-input')

    def town(self):
        s=self.session
        return s.client_build=='dx11_260923'and s.role=='game'and s.phase=='town_ready'

    def merge(self):
        self.metrics['town_moves_coalesced']+=1

    async def _read(self):
        sequence=1
        try:
            while True:
                wire=await self.read()
                frame=decode_frame(wire,self.keys,expected_sequence=sequence);sequence+=1
                event=decode_event(frame.plaintext);self.metrics['requests']+=1
                if self.auxiliary is not None and self.auxiliary(event):
                    self.metrics['auxiliary_coalesced']+=1
                    if sequence%16==0:await asyncio.sleep(0)
                    continue
                request=Request(frame.sequence,event,len(wire),time.perf_counter(),position(event))
                # Neither encrypted wire nor duplicate plaintext escapes here.
                del wire,frame
                async with self.condition:
                    if (request.position and self.moving and self.town()and self.pending
                            and all(p.position for p in self.pending)):
                        prior=self.pending.pop();self.bytes-=prior.size;self.merge()
                    else:
                        await self.condition.wait_for(lambda:len(self.pending)<16 and self.bytes+request.size<=1024*1024)
                    self.pending.append(request);self.bytes+=request.size;self.condition.notify_all()
                if sequence%16==0:await asyncio.sleep(0)
        except asyncio.CancelledError:raise
        except Exception as error:
            async with self.condition:self.error=error;self.condition.notify_all()

    async def get(self):
        async with self.condition:
            await self.condition.wait_for(lambda:self.pending or self.error is not None)
            if not self.pending:raise self.error
            request=self.pending.popleft();self.bytes-=request.size
            self.moving=request.position and self.town()
            while self.moving and self.pending and self.pending[0].position:
                request=self.pending.popleft();self.bytes-=request.size;self.merge()
            self.condition.notify_all();return request

    async def close(self):
        self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)
        self.pending.clear();self.bytes=0;self.error=None
