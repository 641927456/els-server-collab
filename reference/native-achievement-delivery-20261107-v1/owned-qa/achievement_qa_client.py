"""Ordinary requests against three enrolled identities; no synthetic completions."""
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


def mail_request(recipient, item):
    from els_server.protocol.player_mail_messages import grammars, send_request
    from els_server.protocol.local_messages import wstring
    values = dict(recipient=recipient, title='Owned achievement QA', body='Finite owned fixture',
        ed=0, item=item, count=1, flag=0, extra=0)
    parts = []
    for field in grammars()[0]['fields']:
        kind = field['kind']
        if kind == 'noise':
            parts.append(struct.pack('>I', 4)+b'ownq')
        elif kind == 'wstring':
            parts.append(wstring(values[field['field']]))
        else:
            parts.append((values[field['field']]^int(field['mask'],0)).to_bytes(
                {'byte':1,'u32':4,'u64':8}[kind], 'big'))
    payload = b''.join(parts)
    assert send_request(payload) == values
    return payload


async def scenario(identities, snapshot, report):
    from els_server.domain.achievement_catalog import points
    peers = []
    def ids(row):
        return {r['id'] for r in row['achievement']['completed']}
    async def success(p, kind, body=b'', reply=None):
        answer = await p.query(kind, body, reply)
        assert answer.payload[:4] == bytes(4), (hex(kind), answer.payload[:16].hex())
        return answer
    async def verify(p, row):
        await p.query(0x6be)
        expected = points(row['achievement']['completed'])
        status = next(e for e in reversed(p.received) if e.kind == 0x6c7).payload
        n = len(row['achievement']['watched'])
        assert status == struct.pack('>I4iI',4,*expected,n)+b''.join(struct.pack('>i',v) for v in row['achievement']['watched'])+b'\0'
    try:
        assert len(identities) == 3
        for identity in identities:
            await connect(identity, peers)
        first, other, receiver = peers
        initial = snapshot()
        assert ids(initial[0]) == {19,20,21,73,74,75}
        assert ids(initial[1]) == ids(initial[2]) == set()
        await verify(first, initial[0])
        await success(first, 0x6c1, struct.pack('>i',19))
        assert snapshot()[0]['achievement']['watched'] == [19]
        for _ in range(5):
            item = next(i for i in snapshot()[0]['items'] if i['template'] == 77000)
            await success(first, 0x1cf, mail_request(identities[2]['character_name'],item['uid']))
        after = snapshot()
        assert ids(after[0]) == ids(initial[0]) | {155}
        assert ids(after[1]) == ids(after[2]) == set()
        assert after[2]['mail_total'] == 5
        assert not any(i['template']==77000 for i in after[0]['items'])
        await first.query(0x48d,reply=0x48f)
        assert any(e.kind==0x6c0 for e in first.received)
        assert not any(e.kind==0x6c0 for e in other.received+receiver.received)
        await first.close()
        peers.remove(first)
        alt = await connect(identities[0]['alt'], peers)
        current = snapshot()
        assert ids(current[3]) == ids(current[0]) and current[3]['achievement']['watched'] == []
        await verify(alt, current[3])
        for _ in range(2):
            ack = await success(alt, 0x6c9, struct.pack('>i',21))
            assert ack.payload[-1:] == b'\1'
        mailed = snapshot()
        assert mailed[0]['mail_total'] == 0 and mailed[3]['mail_total'] == 1
        letter = mailed[3]['mails'][0]
        assert letter['item']['template'] == 118204 and letter['item']['count'] == 20
        await success(alt,0x1d2,struct.pack('>Q',letter['id']))
        for _ in range(2):
            await success(alt,0x1d4,struct.pack('>IQ',1,letter['id'])+bytes(6))
        claimed = snapshot()
        assert sum(i['count'] for i in claimed[3]['items'] if i['template']==118204) == 20
        await alt.close()
        peers.remove(alt)
        cold = await connect(identities[0], peers)
        final = snapshot()
        assert final[0]['achievement']['watched'] == [19] and final[3]['achievement']['watched'] == []
        assert ids(final[0]) == ids(final[3]) == ids(after[0])
        assert next(r for r in final[0]['achievement']['completed'] if r['id']==21)['received']
        await verify(cold,final[0])
        report.update(ok=True,checks=[
            'Three separately enrolled accounts authenticate through pinned TLS and ordinary town entry',
            'Authoritative profession/ERP fixture cold-loads six account completions with exact native summary',
            'Five ordinary committed post receipts complete155 once; foreign accounts get no completion',
            'Alternative character shares account completion and keeps its own display list',
            'Repeated native6C9 creates one recipient-owned20mithril mail; repeated native attachment claim grants20 once',
            'Fresh ordinary character login retains completion, received marker and independent display'],
            natural_GUI=False,natural_profession_growth=False,natural_battle=False,fixture_accounts=3,fixture_characters=4)
    finally:
        for p in peers:
            await p.close()
