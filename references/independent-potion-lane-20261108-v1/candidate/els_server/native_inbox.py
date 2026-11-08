"""Bounded native input; coalesce only consecutive validated town positions."""
import asyncio
import hashlib
import json
import time
from collections import deque
from dataclasses import dataclass
from els_server.protocol.protocol_codec import ProtocolError,decode_frame,decode_event
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
    def __init__(self,read,keys,session,metrics,*,auxiliary=None,independent=None):
        self.read=read;self.keys=keys;self.session=session;self.metrics=metrics
        self.pending=deque();self.bytes=0;self.condition=asyncio.Condition()
        self.error=None;self.moving=False
        self.auxiliary=auxiliary
        self.independent=independent;self.current=None;self.current_done=None
        self.task=asyncio.create_task(self._read(),name='native-input')

    def town(self):
        s=self.session
        return s.client_build=='dx11_260923'and s.role=='game'and s.phase=='town_ready'

    def merge(self):
        self.metrics['town_moves_coalesced']+=1

    async def _read(self):
        sequence=1;secure_sequences={};last_authenticated=None
        try:
            while True:
                wire=await self.read()
                frame=decode_frame(wire,self.keys,expected_sequence=sequence);sequence+=1
                # The outer sequence is outside the MAC. Preserve the native
                # per-SPI counter, including its nonzero uint32 wrap rule.
                previous=secure_sequences.get(frame.spi,0)
                if (not frame.secure_sequence or frame.secure_sequence==previous
                        or frame.secure_sequence<previous and previous!=0xffffffff):
                    # Keep only the preceding frame's digests in memory. Emit
                    # equality flags, never a packet, fingerprint, IV or key.
                    adjacent=last_authenticated is not None and last_authenticated[:2]==(frame.spi,previous)
                    try:rejected=decode_event(frame.plaintext)
                    except ProtocolError:rejected=None
                    detail=dict(compared_adjacent=adjacent,
                        same_authenticated_body=(hashlib.sha256(memoryview(wire)[8:]).digest()==last_authenticated[2])if adjacent else None,
                        same_plaintext=(hashlib.sha256(frame.plaintext).digest()==last_authenticated[3])if adjacent else None,
                        previous_kind=last_authenticated[4]if adjacent else None,
                        received_kind=rejected.kind if rejected is not None else None,
                        received_plaintext_bytes=len(frame.plaintext))
                    raise ProtocolError(f'Unexpected secure sequence (spi={frame.spi}, previous={previous}, received={frame.secure_sequence}, outer={frame.sequence}); correlation='+json.dumps(detail,separators=(',',':')))
                secure_sequences[frame.spi]=frame.secure_sequence
                event=decode_event(frame.plaintext);self.metrics['requests']+=1
                last_authenticated=(frame.spi,frame.secure_sequence,
                    hashlib.sha256(memoryview(wire)[8:]).digest(),
                    hashlib.sha256(frame.plaintext).digest(),event.kind)
                if self.auxiliary is not None and self.auxiliary(event):
                    self.metrics['auxiliary_coalesced']+=1
                    if sequence%16==0:await asyncio.sleep(0)
                    continue
                request=Request(frame.sequence,event,len(wire),time.perf_counter(),position(event))
                # Neither encrypted wire nor duplicate plaintext escapes here.
                del wire,frame
                if self.independent is not None and await self.independent(request,self):continue
                async with self.condition:
                    if (request.position and self.moving and self.town()and self.pending
                            and all(p.position for p in self.pending)):
                        prior=self.pending.pop();self.bytes-=prior.size;self.merge()
                    else:
                        # Authenticate a bounded lookahead so a potion behind
                        # a combat burst can reach its independent lane.
                        await self.condition.wait_for(lambda:len(self.pending)<128 and self.bytes+request.size<=1024*1024)
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
            self.current=request
            self.current_done=asyncio.get_running_loop().create_future()
            self.condition.notify_all();return request

    def completed(self,request):
        if self.current is request:
            self.current=None
            if self.current_done is not None:self.current_done.set_result(None)
            self.current_done=None

    async def close(self):
        self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)
        self.pending.clear();self.bytes=0;self.error=None
        self.current=None;self.current_done=None;self.independent=None
