"""Abrupt native disconnection, remaining host promotion and empty-room teardown."""
import struct
from combined_qa_client import connect
from els_server.protocol import photo_zone_messages as wire


async def scenario(identities, snapshot, report):
    peers = []
    try:
        for identity in identities:
            await connect(identity, peers)
        before = snapshot()
        created = await peers[0].query(0x5a2, wire.room(world=689, name='OwnedLifecycle'))
        assert created.payload[:4] == bytes(4)
        room_id = struct.unpack_from('>Q', created.payload, 5)[0]
        for index in (1, 2):
            answer = await peers[index].query(0x5a4, struct.pack('>Q', room_id) + wire.wstring(''))
            assert answer.payload[:4] == bytes(4)
        host = peers.pop(0)
        await host.close()
        # Closing a TCP socket completes asynchronously on the server. Its
        # native 5A9 is the release boundary, before the promoted host acts.
        notice = await peers[0].until(0x5a9)
        assert notice.payload[1:9] == struct.pack('>Q', identities[0]['uid'])
        answer = await peers[0].query(0x5b4, b'\1' + wire.wstring('OwnedAfterDrop') + wire.wstring('') + struct.pack('>H', 690))
        assert answer.payload[:4] == bytes(4)
        report['checks'].append('Abrupt host disconnection sends native leave and promotes an existing member with working settings authority')
        guest = peers.pop()
        await guest.close()
        notice = await peers[0].until(0x5a9)
        assert notice.payload[1:9] == struct.pack('>Q', identities[2]['uid'])
        last = peers.pop()
        await last.close()
        fresh = await connect(identities[1], peers)
        # Reconnection to the same actor waits on its existing release queue.
        # The old room must not remain joinable after all members disconnected.
        denied = await fresh.query(0x5a4, struct.pack('>Q', room_id) + wire.wstring(''))
        assert denied.payload[:4] != bytes(4)
        listed = await fresh.query(0x5ac, struct.pack('>iH', 1, 65535))
        assert listed.payload[:4] == bytes(4)
        assert wire.wstring('OwnedAfterDrop') not in listed.payload
        assert snapshot() == before
        report['checks'].append('All disconnected members remove the room; cold actor cannot rejoin it and no saved location or asset changes occur')
        report['ok'] = True
    finally:
        for peer in reversed(peers):
            await peer.close()
