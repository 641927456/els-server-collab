import asyncio,ssl,struct
from els_server.protocol.protocol_codec import Event,encode_event,encode_frame,decode_event,decode_frame
class Peer:

    async def send(self, kind, payload=b''):
        self.writer.write(encode_frame(encode_event(Event(514, kind=kind, payload=payload, performers=(0,))), self.keys, spi=self.spi, sequence=self.outgoing))
        self.outgoing += 1
        await self.writer.drain()

    async def until(self, kind):
        async with asyncio.timeout(12):
            for _ in range(240):
                header = await self.reader.readexactly(8)
                wire = header + await self.reader.readexactly(struct.unpack_from('<I', header)[0] - 8)
                event = decode_event(decode_frame(wire, self.keys, expected_sequence=self.incoming).plaintext)
                self.incoming += 1
                self.received.append(event)
                if event.kind == kind:
                    return event
        raise AssertionError('Missing response ' + hex(kind))

    async def query(self, kind, payload, reply):
        await self.send(kind, payload)
        event = await self.until(reply)
        await self.send(1165)
        await self.until(1167)
        return event

    async def close(self):
        self.writer.close()
        try:
            await self.writer.wait_closed()
        except ssl.SSLError as error:
            if error.reason != 'APPLICATION_DATA_AFTER_CLOSE_NOTIFY':
                raise
        await self.bridge.close()
