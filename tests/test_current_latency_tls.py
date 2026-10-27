"""Current framed TLS operations on owned temporary actors; no GUI or combat claim."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import struct
import tempfile
import unittest

from test_friends_server import FriendsTests,Peer,read_wire
from els_server.protocol.protocol_codec import Event,encode_frame,encode_event


class CurrentLatencyTLS(FriendsTests):
    # Load only explicitly named tests from this subclass. Legacy inherited
    # gameplay scenarios remain in their original suite and failure inventory.
    async def test_current_auxiliary_burst_external_revocation_and_timings(self):
        alice,bob=await asyncio.gather(self.peer(self.alice),self.peer(self.bob))
        await asyncio.gather(alice.roster(),bob.roster())
        a=self.app.accounts[self.alice['id']].uid;b=self.app.accounts[self.bob['id']].uid
        await alice.enter_town(a);await bob.enter_town(b)
        async def burst(peer):
            for _ in range(128):
                event=Event(0x202,kind=0x7d0,payload=bytes(9),performers=(0,))
                peer.writer.write(encode_frame(encode_event(event),peer.keys,spi=peer.spi,sequence=peer.outgoing))
                peer.outgoing+=1
            await peer.writer.drain()
            # A current owned inventory query is the fence after the no-op
            # burst; it grants no item, currency, effect or clear reward.
            await peer.send(0x213)
            await peer.until(0x214)
        await asyncio.gather(burst(alice),burst(bob))
        operations=self.app.performance.snapshot()
        self.assertEqual(operations['handle']['errors'],0)
        self.assertGreaterEqual(operations['handle']['count'],256)
        timings=[e for e in self.events if e['event']=='request_timing' and e['kind']==0x7d0]
        self.assertGreaterEqual(len(timings),2)
        for row in timings:
            self.assertTrue(row['reply_complete'])
            self.assertEqual(len(row['calls']),1)
            self.assertFalse(row['calls'][0]['failed'])
            self.assertGreaterEqual(row['calls'][0]['registry_checks'],1)
        # The persistent enabled reader must see this independent committed
        # writer immediately; the existing 50 ms periodic exit revokes Bob.
        self.app.registry.disable(self.bob['name'])
        await asyncio.wait_for(bob.reader.read(),3)
        for _ in range(100):
            if self.bob['id'] not in self.app.playing:break
            await asyncio.sleep(.01)
        self.assertNotIn(self.bob['id'],self.app.playing)
        self.assertIn(self.alice['id'],self.app.playing)
        self.assertFalse(any(e['event']=='worker_error' for e in self.events))

    async def test_current_selection_rejects_bad_native_envelope(self):
        peer=await self.peer(self.alice);await peer.roster()
        uid=self.app.accounts[self.alice['id']].uid
        await peer.send(0x490);await peer.until(0x491)
        bad=Event(0x202,kind=0x28,payload=struct.pack('>Q',uid),performers=())
        peer.writer.write(encode_frame(encode_event(bad),peer.keys,spi=peer.spi,sequence=peer.outgoing))
        peer.outgoing+=1;await peer.writer.drain()
        await asyncio.wait_for(peer.reader.read(),3)
        self.assertNotIn(self.alice['id'],self.app.playing)
        self.assertTrue(any(e['event']=='protocol_error' and e['error']=='Invalid character initialization envelope' for e in self.events))


def load_tests(loader,tests,pattern):
    return unittest.TestSuite(CurrentLatencyTLS(name) for name in (
        'test_current_auxiliary_burst_external_revocation_and_timings',
        'test_current_selection_rejects_bad_native_envelope'))


if __name__=='__main__':unittest.main()
