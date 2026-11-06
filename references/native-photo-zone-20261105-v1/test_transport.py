"""Exercise all studio peer sockets and stable gaps with private UDP only."""
import bootstrap as env
import asyncio,copy,json,uuid,unittest
from types import SimpleNamespace
from els_server.friends_relay import RelayClient,read_data

class Receiver(asyncio.DatagramProtocol):
    def __init__(self):self.queue=asyncio.Queue()
    def datagram_received(self,data,address):self.queue.put_nowait((data,address))

class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.loop=asyncio.get_running_loop()
        self.native,self.received=await self.loop.create_datagram_endpoint(Receiver,local_addr=('127.0.0.1',0))
        self.client=RelayClient(SimpleNamespace(game_address=self.native.get_extra_info('sockname')))
        self.manifest=dict(epoch=str(uuid.uuid4()),uid=9001,
            peers=[dict(uid=9001+i,port=21100+i)for i in range(8)])
    async def asyncTearDown(self):
        await self.client.configure(None)
        self.native.close()
    async def exchange(self,peer):
        payload=('studio-peer-'+str(peer['uid'])).encode()
        self.native.sendto(payload,('127.0.0.1',peer['port']))
        packet=await asyncio.wait_for(self.client.outgoing.get(),2)
        self.assertEqual(read_data(packet),(self.manifest['epoch'],peer['uid'],payload))
        # The original bridge uses this same proxy to deliver the authenticated
        # server packet; assert the native-facing sender port is unchanged.
        reply=b'opaque-'+payload
        self.client.proxies[peer['uid']][0].sendto(reply,self.client.bridge.game_address)
        self.assertEqual(await asyncio.wait_for(self.received.queue.get(),2),
            (reply,('127.0.0.1',peer['port'])))
    async def test_eight_member_roster_each_peer_transmits_both_directions(self):
        await self.client.configure(self.manifest)
        self.assertEqual(len(self.client.proxies),7)
        for peer in self.manifest['peers'][1:]:await self.exchange(peer)
    async def test_departed_slot_stays_empty_and_rejoins_without_moving_survivor_ports(self):
        await self.client.configure(self.manifest)
        reduced=copy.deepcopy(self.manifest)
        reduced['peers']=[p for p in reduced['peers']if p['uid']not in(9002,9004)]
        await self.client.configure(reduced)
        self.assertNotIn(9002,self.client.proxies)
        await self.exchange(reduced['peers'][-1])
        await self.client.configure(self.manifest)
        await self.exchange(self.manifest['peers'][1])
    async def test_invalid_manifest_never_tears_down_current_sockets(self):
        await self.client.configure(self.manifest)
        originals=dict(self.client.proxies)
        variants=[]
        bad=copy.deepcopy(self.manifest);bad['peers'][1]['port']=21100;variants.append(bad)
        bad=copy.deepcopy(self.manifest);bad['peers'][-1]['port']=21108;variants.append(bad)
        bad=copy.deepcopy(self.manifest);bad['peers'][-1]['uid']=9002;variants.append(bad)
        bad=copy.deepcopy(self.manifest);bad['peers'].append(dict(uid=9010,port=21109));variants.append(bad)
        for bad in variants:
            with self.assertRaises(ValueError):await self.client.configure(bad)
            self.assertEqual(self.client.proxies,originals)
        await self.exchange(self.manifest['peers'][-1])

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TransportTests))
    (env.HERE/'transport-tests.json').write_text(json.dumps(dict(passed=result.wasSuccessful(),
        tests=result.testsRun,private_UDP=True,game_process_access=False,
        full_native_scene=False),indent=2),encoding='utf-8')
    raise SystemExit(not result.wasSuccessful())
