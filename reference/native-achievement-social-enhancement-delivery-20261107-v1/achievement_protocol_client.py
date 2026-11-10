"""Reuse the accepted ordinary native peer and login without unrelated scenarios."""
import asyncio, ssl, struct

from els_server.friends_bridge import Bridge, BridgeConfig

from els_server.protocol.protocol_codec import BOOTSTRAP_KEYS, Event, encode_event, encode_frame, decode_frame, decode_event, read_welcome

class Peer:
    async def send(self, kind, payload=b''):
        self.writer.write(encode_frame(encode_event(Event(0x202, kind=kind, payload=payload, performers=(0,))),
            self.keys, spi=self.spi, sequence=self.outgoing))
        self.outgoing += 1
        await self.writer.drain()

    async def until(self, kind):
        async with asyncio.timeout(25):
            for _ in range(400):
                head = await self.reader.readexactly(8)
                raw = head+await self.reader.readexactly(struct.unpack_from('<I', head)[0]-8)
                event = decode_event(decode_frame(raw, self.keys, expected_sequence=self.incoming).plaintext)
                self.incoming += 1
                self.received.append(event)
                if event.kind in (kind if isinstance(kind, tuple) else (kind,)):
                    return event
        raise AssertionError('Native reply missing '+hex(kind))

    async def query(self, kind, payload=b'', reply=None):
        await self.send(kind, payload)
        answer = await self.until(kind+1 if reply is None else reply)
        await self.send(0x48d)
        await self.until(0x48f)
        return answer

    async def close(self):
        self.writer.close()
        try:
            await self.writer.wait_closed()
        except ssl.SSLError as error:
            if error.reason != 'APPLICATION_DATA_AFTER_CLOSE_NOTIFY':
                raise
        await self.bridge.close()

async def connect(identity, peers):
    from els_server.domain.town_travel import catalog
    p = Peer()
    p.bridge = Bridge(BridgeConfig(**identity['bridge']))
    p.reader, p.writer = await p.bridge.remote()
    p.keys, p.incoming, p.received = BOOTSTRAP_KEYS, 1, []
    peers.append(p)
    p.spi, p.keys = read_welcome(await p.until(1))
    p.outgoing = 1
    for kind, reply in ((0x1a,0x1b),(0x1e,0x19c),(0x35,0x36),(0x1ef,0x1f0),(0x39,0x3a),(0x485,0x488)):
        await p.send(kind)
        await p.until(reply)
    xyz = catalog()['towns']['20001']['xyz']
    for kind, reply, body in ((0x490,0x491,b''),(0x28,0x29,struct.pack('>Q',identity['uid'])),
        (0x6e9,0x6ea,b''),(0x5bf,0x5c0,bytes(8)),(0x32,0x33,b''),
        (0x225,0x226,struct.pack('>iB',20001,0)),(0x227,0x228,struct.pack('>fffBH',*xyz,0,0))):
        await p.send(kind, body)
        answer = await p.until(reply)
        if kind in (0x225, 0x227):
            assert answer.payload[:4] == bytes(4)
    await p.send(0x48d)
    await p.until(0x48f)
    return p
