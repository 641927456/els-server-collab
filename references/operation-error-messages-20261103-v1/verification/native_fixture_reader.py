"""Continuous native load-client reader; request deadlines remain eight seconds."""
import asyncio,struct
from collections import deque
from els_server.protocol.protocol_codec import decode_frame,decode_event


def install(fixture):
    original_open=fixture.Peer.open.__func__
    original_close=fixture.Peer.close

    async def open(cls,bridge):
        peer=await original_open(cls,bridge)
        peer.observed=deque(maxlen=180);peer.pending=asyncio.Queue(1024)
        async def receive():
            try:
                while True:
                    header=await peer.reader.readexactly(8)
                    length=struct.unpack_from('<I',header)[0]
                    assert 40<=length<=1024*1024
                    wire=header+await peer.reader.readexactly(length-8)
                    frame=decode_frame(wire,peer.keys,expected_sequence=peer.incoming);peer.incoming+=1
                    event=decode_event(frame.plaintext)
                    peer.observed.append(dict(received=event.kind,sequence=frame.sequence))
                    peer.pending.put_nowait(event)
            except Exception as error:
                peer.pending.put_nowait(error)
        peer.receiving=asyncio.create_task(receive(),name='owned-native-reader')
        return peer

    async def until(self,kind):
        async with asyncio.timeout(8):
            while True:
                event=await self.pending.get()
                if isinstance(event,Exception):raise event
                if event.kind==kind:return event

    async def close(self):
        self.receiving.cancel();await asyncio.gather(self.receiving,return_exceptions=True)
        await original_close(self)

    fixture.Peer.open=classmethod(open)
    fixture.Peer.until=until
    fixture.Peer.close=close
