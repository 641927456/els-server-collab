"""Real TLS/native framing: authentication, account ownership, leases and reconnects."""
import asyncio
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import ssl
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import time
import uuid

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.friends_bridge import Bridge,BridgeConfig
from els_server.protocol.protocol_codec import BOOTSTRAP_KEYS,Event,encode_event,encode_frame,decode_frame,decode_event,read_welcome
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.lifecycle import prepare_database
from els_server.transport import GameServer


async def read_wire(reader):
    async with asyncio.timeout(5):
        header=await reader.readexactly(8)
        return header+await reader.readexactly(struct.unpack_from('<I',header)[0]-8)


class Peer:
    @classmethod
    async def open(cls,bridge):
        peer=cls();peer.reader,peer.writer=await bridge.remote()
        peer.spi,peer.keys=read_welcome(decode_event(decode_frame(await read_wire(peer.reader),BOOTSTRAP_KEYS).plaintext))
        peer.outgoing=1;peer.incoming=2
        return peer

    async def send(self,kind,payload=b'',event_id=0x202):
        if kind==0x5bf and payload==b'':payload=bytes(8)
        self.writer.write(encode_frame(encode_event(Event(event_id,kind=kind,payload=payload,performers=(0,) if kind in (0xad,0x28) else ())),self.keys,spi=self.spi,sequence=self.outgoing))
        self.outgoing+=1;await self.writer.drain()

    async def until(self,kind):
        async with asyncio.timeout(8):
            for _ in range(40):
                frame=decode_frame(await read_wire(self.reader),self.keys,expected_sequence=self.incoming);self.incoming+=1
                event=decode_event(frame.plaintext)
                if event.kind==kind:return event
        raise AssertionError('Expected native response missing: '+hex(kind))

    async def roster(self):
        for request,response in ((0x1a,0x1b),(0x1e,0x19c),(0x35,0x36),(0x1ef,0x1f0),(0x39,0x3a),(0x485,0x488)):
            await self.send(request);reply=await self.until(response)
        return reply

    async def close(self):
        self.writer.close()
        try:await self.writer.wait_closed()
        except ssl.SSLError as error:
            # A town broadcast can already be in flight when this test peer
            # initiates TLS shutdown. No application reads follow close().
            if error.reason!='APPLICATION_DATA_AFTER_CLOSE_NOTIFY':raise

    async def enter_town(self,uid,town=20000):
        for kind,response,payload in ((0x490,0x491,b''),(0x28,0x29,struct.pack('>Q',uid)),
            (0x6e9,0x6ea,b''),(0x5bf,0x5c0,b''),(0x32,0x33,b''),
            (0x225,0x226,struct.pack('>iB',town,0)),(0x227,0x228,struct.pack('>fffBH',1.,2.,3.,0,0))):
            await self.send(kind,payload);await self.until(response)

    async def invite(self,other,uid,name,own_uid):
        from els_server.protocol.local_messages import wstring
        payload=struct.pack('>Q',uid)+wstring(name)+struct.pack('>iBi',0,1,30000)+bytes(6)+wstring('')+bytes(15)
        await self.send(0x136,payload);await self.until(0x137);await other.until(0x138)
        await other.send(0x139,struct.pack('>QQBiBQ',own_uid,uid,1,0,0,0))
        await other.until(0x13a);await asyncio.gather(self.until(0x13b),other.until(0x13b))


class FriendsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT);self.root=Path(self.tmp.name)
        cert_dir=Path(os.environ.get('ELS_TEST_CERT_DIR',self.root))
        if 'ELS_TEST_CERT_DIR' in os.environ:
            import ssl
            der=ssl.PEM_cert_to_DER_cert((cert_dir/'server-cert.pem').read_text())
            self.pin=hashlib.sha256(der).hexdigest()
        else:
            from tools.create_friends_certificate import create
            self.pin=create(self.root,'127.0.0.1')
        self.config=ServerConfig(mode='friends',port=0,state_file=self.root/'game.sqlite3',accounts_file=self.root/'accounts.sqlite3',tls_cert=cert_dir/'server-cert.pem',tls_key=cert_dir/'server-key.pem',log_dir=self.root/'logs')
        prepare_database(self.config.state_file)
        self.app=Application(self.config);await self.app.start()
        self.alice=self.app.registry.create('alice');self.bob=self.app.registry.create('bob')
        self.events=[]
        self.server=GameServer(self.config,self.app,lambda event,**kw:self.events.append(dict(event=event,**kw)))
        _,self.port=await self.server.start();self.peers=[];self.bridges=[]

    def bridge(self,account,**overrides):
        config=BridgeConfig('127.0.0.1',self.port,account['name'],account['token'],self.pin)
        bridge=Bridge(replace(config,**overrides));self.bridges.append(bridge);return bridge

    async def peer(self,account):
        # Gameplay regression fixtures explicitly create their own characters.
        # First-login/empty-roster tests open Peer directly instead.
        identity=self.app.registry.authenticate(account['name'],account['token'])
        roster=Characters(self.config.state_file,identity['id'])
        if not roster.list():roster.create('Player'+str(identity['id']),1,'test-initial:'+str(identity['id']))
        peer=await Peer.open(self.bridge(account));self.peers.append(peer);return peer

    async def asyncTearDown(self):
        for peer in self.peers:
            try:await peer.close()
            except (OSError,ConnectionError):pass
        for bridge in self.bridges:await bridge.close()
        await self.server.close();self.app.close();self.tmp.cleanup()

    async def test_authentication_and_certificate_pin(self):
        with self.assertRaisesRegex(ValueError,'fingerprint'):await self.bridge(self.alice,certificate_sha256='0'*64).remote()
        with self.assertRaisesRegex(ValueError,'authentication'):await self.bridge(self.alice,token='x'*43).remote()
        self.assertFalse(self.app.accounts)
        peer=await self.peer(self.alice)
        await peer.send(0x274,event_id=0x402)
        identity=await peer.until(0x275)
        self.assertEqual(struct.unpack_from('>Q',identity.payload,4)[0],self.alice['id'])
        encoded=json.dumps(self.events)
        self.assertNotIn(self.alice['token'],encoded);self.assertNotIn(self.bob['token'],encoded)

    async def coop_pair(self):
        self.config=replace(self.config,friends_coop_enabled=True)
        self.app.config=self.config;self.server.config=self.config
        alice,bob=await asyncio.gather(self.peer(self.alice),self.peer(self.bob))
        await asyncio.gather(alice.roster(),bob.roster())
        a=self.app.accounts[self.alice['id']].uid;b=self.app.accounts[self.bob['id']].uid
        await alice.enter_town(a);await bob.enter_town(b)
        await alice.invite(bob,b,'Player'+str(self.bob['id']),a)
        return alice,bob,a,b

    async def coop_start(self,alice,bob,identity=30000,load=True):
        await bob.send(0x14c,b'\1'+bytes(4))
        own=self.app.accounts[self.bob['id']].uid
        while struct.unpack_from('>Q',(await bob.until(0x14d)).payload,4)[0]!=own:pass
        await alice.until(0x14d)
        await alice.send(0x7d4,struct.pack('>ii',1,identity))
        self.assertEqual((await alice.until(0x7d5)).payload[:4],bytes(4))
        entry=bytes.fromhex('eefc726aad751f003e6b6d2e0c4d36e2923600000010332b6d21282a5c1774790f0f3a4c7947')
        await alice.send(0x382,entry);await alice.until(0x383)
        packets=await asyncio.gather(alice.until(0x14a),bob.until(0x14a))
        self.assertEqual(packets[0].payload,packets[1].payload)
        for uid in (self.app.accounts[self.alice['id']].uid,self.app.accounts[self.bob['id']].uid):
            self.assertIn(struct.pack('>Q',uid),packets[0].payload)
        if not load:return
        await alice.send(0x91,struct.pack('>ii',100,0));await alice.until(0x92)
        self.assertEqual({s.phase for s in self.app.playing.values()},{'dungeon_loading'})
        await bob.send(0x91,struct.pack('>ii',100,0));await bob.until(0x92)
        initial=await asyncio.gather(alice.until(0xb2),bob.until(0xb2))
        self.assertEqual(initial[0].payload,initial[1].payload)

    async def coop_load(self,alice,bob):
        await alice.send(0xb3,bytes(9));await alice.until(0xb4)
        self.assertTrue(all(not s.dungeon_substage_synced for s in self.app.playing.values()))
        await bob.send(0xb3,bytes(9));await bob.until(0xb4)
        await asyncio.gather(alice.until(0xbd),bob.until(0xbd))
        self.assertTrue(all(s.dungeon_substage_synced for s in self.app.playing.values()))

    async def test_shared_dungeon_barriers_master_auth_and_durable_rewards(self):
        from els_server.domain.dungeon_population import population
        alice,bob,a,b=await self.coop_pair()
        # Readiness and leader authorization are checked before allocating a run.
        await alice.send(0x7d4,struct.pack('>ii',1,30000))
        self.assertEqual((await alice.until(0x7d5)).payload[:4],struct.pack('>i',2224))
        await bob.send(0x7d4,struct.pack('>ii',1,30000))
        self.assertEqual((await bob.until(0x7d5)).payload[:4],struct.pack('>i',2224))
        await self.coop_start(alice,bob)
        sessions=list(self.app.playing.values());before={s.account.uid:s.account.get_reward_balances()['ed'] for s in sessions}
        self.assertEqual(len({s.reward_run_id for s in sessions}),2)
        self.assertIs(self.app.world.dungeons.room(sessions[0]),self.app.world.dungeons.room(sessions[1]))
        def report(npc,killer=b):
            return (struct.pack('>iBQQ6fBf',npc['key'],0,a,killer,0.,0.,0.,1.,2.,3.,0,npc['hp'])
                +struct.pack('>IQf',1,killer,1.)+struct.pack('>IQB',1,killer,1)+bytes(8)+bytes(4)+struct.pack('>Q',killer))
        for stage in range(3):
            await self.coop_load(alice,bob)
            p=population(stage)
            order=[n for n in p['npcs'] if n['key']!=p['clear_key']]+[p['npcs'][p['clear_key']]]
            # A guest cannot report authoritative kills, nor can a master name
            # an unrelated character as a contributor/killer.
            await bob.send(0xad,report(order[0]))
            await alice.send(0xad,report(order[0],b+999))
            await asyncio.sleep(.08)
            self.assertTrue(all(not s.defeated_npcs for s in sessions))
            for npc in order:
                await alice.send(0xad,report(npc));await alice.until(0xae)
                death=await bob.until(0xaf)
                self.assertEqual(struct.unpack_from('>Q',death.payload,9)[0],b)
            self.assertTrue(all(s.part_end_notified for s in sessions))
            await alice.send(0xbb,b'\0');await alice.until(0xbc)
            await alice.send(0xbb,b'\0');await alice.until(0xbc)
            self.assertTrue(all(s.gate_stage==stage for s in sessions))
            await bob.send(0xbb,b'\0');await bob.until(0xbc)
            if stage<2:
                pages=await asyncio.gather(alice.until(0xb2),bob.until(0xb2))
                self.assertEqual(pages[0].payload,pages[1].payload)
            else:
                await asyncio.gather(alice.until(0xc1),bob.until(0xc1))
        self.assertTrue(all(s.clear_notified for s in sessions))
        balances={s.account.uid:s.account.get_reward_balances()['ed'] for s in sessions}
        self.assertTrue(all(balances[s.account.uid]>before[s.account.uid] for s in sessions))
        await alice.send(0xbb,b'\0');await alice.until(0xbc)
        self.assertEqual(balances,{s.account.uid:s.account.get_reward_balances()['ed'] for s in sessions})
        for s in sessions:
            from els_server.domain.local_session import LocalAccount
            saved=LocalAccount(LocalState(self.config.state_file,s.account.uid))
            self.assertEqual(saved.get_inventory_snapshot()['balances']['ed'],balances[s.account.uid])

    async def test_shared_dungeon_disconnect_aborts_without_reward(self):
        alice,bob,a,b=await self.coop_pair();await self.coop_start(alice,bob)
        sessions=list(self.app.playing.values());before={s.account.uid:s.account.get_reward_balances()['ed'] for s in sessions}
        await bob.close()
        async with asyncio.timeout(5):
            while self.app.world.dungeons.rooms:await asyncio.sleep(.02)
        async with asyncio.timeout(5):
            while await alice.reader.read(65536):pass
        self.assertEqual(before,{s.account.uid:s.account.get_reward_balances()['ed'] for s in sessions})

    async def test_four_member_capacity_and_loading_timeout(self):
        alice,bob,a,b=await self.coop_pair()
        for name in ('charlie','david'):
            identity=self.app.registry.create(name);peer=await self.peer(identity);await peer.roster()
            uid=self.app.accounts[identity['id']].uid;await peer.enter_town(uid)
            await alice.invite(peer,uid,'Player'+str(identity['id']),a)
            await peer.send(0x14c,b'\1'+bytes(4));await peer.until(0x14d)
        party=next(iter(self.app.world.parties.values()));self.assertEqual(len(party['members']),4)
        extra=self.app.registry.create('extra');peer=await self.peer(extra);await peer.roster()
        uid=self.app.accounts[extra['id']].uid;await peer.enter_town(uid)
        from els_server.protocol.local_messages import wstring
        invitation=struct.pack('>Q',uid)+wstring('Player'+str(extra['id']))+struct.pack('>iBi',0,1,30000)+bytes(6)+wstring('')+bytes(15)
        await alice.send(0x136,invitation)
        self.assertEqual((await alice.until(0x137)).payload[:4],struct.pack('>i',-1))
        # Admission requires every current member's readiness, checked again
        # after the confirmation popup. A stale invitation cannot join a run.
        await self.coop_start(alice,bob,load=False)
        room=party['run'];room.deadline=1
        async with asyncio.timeout(5):
            while self.app.world.dungeons.rooms:await asyncio.sleep(.02)
        self.assertIsNone(party['run'])
        self.assertTrue(all(s.reward_receipt is None for s in room.members))

    async def test_combat_relay_native_udp_proxy_room_acl_and_epoch(self):
        from els_server.friends_relay import RelayClient,read_packet,read_data,data_packet
        alice,bob,a,b=await self.coop_pair();await self.coop_start(alice,bob)
        received=asyncio.Queue()
        class GameUDP(asyncio.DatagramProtocol):
            def datagram_received(self,data,address):received.put_nowait((data,address))
        game,_=await asyncio.get_running_loop().create_datagram_endpoint(GameUDP,local_addr=('127.0.0.1',0))
        bridge=self.bridge(self.alice);bridge.game_address=game.get_extra_info('sockname')
        relay=RelayClient(bridge);task=asyncio.create_task(relay.run());writer=None
        try:
            reader,writer=await self.bridge(self.bob).remote(role='relay')
            async with asyncio.timeout(5):
                while relay.manifest is None:
                    if task.done():task.result()
                    await asyncio.sleep(.02)
            manifest=json.loads((await read_packet(reader))[1:]);epoch=manifest['epoch']
            self.assertEqual(epoch,relay.manifest['epoch'])
            # Both game sockets stay on loopback. The destination socket's
            # source port remains the advertised remote peer's virtual port.
            game.sendto(b'\x1fNativeOpaqueCombat',('127.0.0.1',21101))
            packet=await asyncio.wait_for(read_packet(reader),5)
            self.assertEqual(read_data(packet),(epoch,a,b'\x1fNativeOpaqueCombat'))
            def send(epoch,target,data):
                packet=data_packet(epoch,target,data);writer.write(struct.pack('>I',len(packet))+packet)
            # Wrong room epochs, unrelated characters and self targets cannot
            # turn this authenticated connection into an arbitrary UDP relay.
            send(str(uuid.uuid4()),a,b'stale');send(epoch,a+9999,b'foreign');send(epoch,b,b'self')
            send(epoch,a,b'\x1fNativeReply');await writer.drain()
            payload,address=await asyncio.wait_for(received.get(),5)
            self.assertEqual((payload,address),(b'\x1fNativeReply',('127.0.0.1',21101)))
            self.assertTrue(received.empty())
            # An authenticated account outside this room gets no roster/data.
            outsider=self.app.registry.create('charlie')
            r,w=await self.bridge(outsider).remote(role='relay')
            try:
                self.assertIsNone(json.loads((await read_packet(r))[1:]))
                packet=data_packet(epoch,a,b'outsider');w.write(struct.pack('>I',len(packet))+packet);await w.drain()
                await asyncio.sleep(.1);self.assertTrue(received.empty())
            finally:w.close();await w.wait_closed()
        finally:
            task.cancel();await asyncio.gather(task,return_exceptions=True);game.close()
            if writer:writer.close();await writer.wait_closed()

    async def test_town_broadcast_chat_isolation_and_disconnect(self):
        from els_server.protocol.local_messages import wstring
        from els_server.protocol.social_messages import Reader
        alice,bob=await asyncio.gather(self.peer(self.alice),self.peer(self.bob))
        await asyncio.gather(alice.roster(),bob.roster())
        a=self.app.accounts[self.alice['id']].uid;b=self.app.accounts[self.bob['id']].uid
        async def enter(peer,uid,town=20000):
            for kind,response,payload in ((0x490,0x491,b''),(0x28,0x29,struct.pack('>Q',uid)),
                (0x6e9,0x6ea,b''),(0x5bf,0x5c0,b''),(0x32,0x33,b''),
                (0x225,0x226,struct.pack('>iB',town,0)),(0x227,0x228,struct.pack('>fffBH',1.,2.,3.,0,0))):
                await peer.send(kind,payload);await peer.until(response)
        await enter(alice,a)
        self.assertEqual((await alice.until(0x22a)).payload,bytes(8))
        await enter(bob,b)
        for peer,uid in ((alice,b),(bob,a)):
            presence=(await peer.until(0x22a)).payload
            self.assertEqual(struct.unpack_from('>IQ',presence),(1,uid))
        movement=struct.pack('>fffI',12.,2.,3.,1)+bytes([1,1])+struct.pack('>BBHBiiBi',0,0,30,0,0,0,0,0)
        await alice.send(0x22b,movement)
        broadcast=await bob.until(0x22e)
        self.assertEqual(struct.unpack_from('>Qfff',broadcast.payload),(a,12.,2.,3.))
        # Request claims somebody else's name and UID: the server ignores them.
        request=bytes(2)+struct.pack('>Q',b)+wstring('Spoofed')+wstring('Target')+wstring('你好，朋友')+struct.pack('>iQBiQiI',0,0,0,0,12345,-1,0)
        await alice.send(0x85,request)
        self.assertEqual((await alice.until(0x86)).payload,bytes(4))
        notices=await asyncio.gather(alice.until(0x87),bob.until(0x87))
        self.assertEqual(notices[0].payload,notices[1].payload)
        r=Reader(notices[0].payload)
        self.assertEqual((r.scalar('B'),r.scalar('Q'),r.scalar('i'),r.scalar('Q')),(0,self.alice['id'],-1,a))
        self.assertEqual(r.text(),'Player'+str(self.alice['id']))
        self.assertNotIn('Spoofed'.encode('utf-16le'),notices[0].payload)
        # A cross-town departure is visible and no old roster remains.
        await bob.send(0x225,struct.pack('>iB',20001,0));await bob.until(0x226)
        removed=await alice.until(0x22a)
        self.assertEqual(removed.payload,struct.pack('>IIQ',0,1,b))
        await bob.send(0x227,struct.pack('>fffBH',4.,5.,6.,0,0));await bob.until(0x228)
        self.assertEqual((await bob.until(0x22a)).payload,bytes(8))
        await bob.close()
        for _ in range(100):
            if len(self.app.world.members)==1:break
            await asyncio.sleep(.01)
        self.assertEqual(len(self.app.world.members),1)
        self.assertEqual(set(self.app.world.towns),{(1,20000)})

    async def test_party_invitation_binding_ready_chat_and_cleanup(self):
        from els_server.protocol.local_messages import wstring
        alice,bob=await asyncio.gather(self.peer(self.alice),self.peer(self.bob))
        await asyncio.gather(alice.roster(),bob.roster())
        a=self.app.accounts[self.alice['id']].uid;b=self.app.accounts[self.bob['id']].uid
        await alice.enter_town(a);await bob.enter_town(b)
        invitation=struct.pack('>Q',b)+wstring('Player'+str(self.bob['id']))+struct.pack('>iBi',0,1,30000)+bytes(6)+wstring('')+bytes(15)
        await alice.send(0x136,invitation)
        self.assertEqual((await alice.until(0x137)).payload[:4],bytes(4))
        self.assertEqual((await bob.until(0x138)).payload[:16],struct.pack('>QQ',a,b))
        # An invitation is bound to both live characters, not a client-chosen UID.
        await bob.send(0x139,struct.pack('>QQBiBQ',a+99,b,1,0,0,0))
        self.assertEqual((await bob.until(0x13a)).payload[:4],struct.pack('>i',-1))
        self.assertFalse(self.app.world.parties)
        await bob.send(0x139,struct.pack('>QQBiBQ',a,b,1,0,0,0))
        self.assertEqual((await bob.until(0x13a)).payload[:4],bytes(4))
        snapshots=await asyncio.gather(alice.until(0x13b),bob.until(0x13b))
        self.assertEqual(snapshots[0],snapshots[1])
        self.assertIn(('Player'+str(self.alice['id'])).encode('utf-16le'),snapshots[0].payload)
        self.assertIn(('Player'+str(self.bob['id'])).encode('utf-16le'),snapshots[0].payload)
        await bob.send(0x14c,struct.pack('>Bi',1,0))
        for peer in (alice,bob):self.assertEqual((await peer.until(0x14d)).payload[:13],struct.pack('>iQB',0,b,1))
        await alice.send(0x85,bytes([1,0])+bytes(8)+wstring('')*2+wstring('Party message')+struct.pack('>iQBiQiI',0,0,0,0,0,-1,0))
        self.assertEqual((await alice.until(0x86)).payload,bytes(4))
        for peer in (alice,bob):self.assertEqual((await peer.until(0x87)).payload[0],1)
        await bob.close()
        self.assertEqual((await alice.until(0x13c)).payload,struct.pack('>Qi',b,0))
        self.assertFalse(self.app.world.parties);self.assertFalse(self.app.world.party_of)

    async def test_two_accounts_and_cross_account_selection(self):
        alice,bob=await asyncio.gather(self.peer(self.alice),self.peer(self.bob))
        a_roster,b_roster=await asyncio.gather(alice.roster(),bob.roster())
        a=self.app.accounts[self.alice['id']];b=self.app.accounts[self.bob['id']]
        self.assertNotEqual(a.uid,b.uid)
        self.assertIn(('Player'+str(self.alice['id'])).encode('utf-16le'),a_roster.payload)
        self.assertNotIn(('Player'+str(self.alice['id'])).encode('utf-16le'),b_roster.payload)
        self.assertEqual([c['uid'] for c in Characters(self.config.state_file,self.alice['id']).list()],[a.uid])
        with self.assertRaises(ValueError):a.for_character(b.uid)
        receipt=await self.app.call(a.enable_rewards().grant,str(uuid.uuid4()),b'friends-isolation',123,0,item_plan=[dict(template=77000,metadata=2,group=6,quantity=2)],inventory_response_builder=lambda balances,items:b'OK')
        self.assertEqual(receipt['balances']['ed'],123)
        self.assertEqual(b.get_reward_balances()['ed'],0)
        self.assertEqual(LocalState(self.config.state_file,a.uid).load()['map'],20000)
        await alice.send(0x490);await alice.until(0x491)
        await alice.send(0x28,struct.pack('>Q',b.uid))
        self.assertEqual(await asyncio.wait_for(alice.reader.read(),5),b'')
        self.assertNotIn(self.alice['id'],self.app.playing)
        # Restart the application and authenticate with the saved registry.
        await self.server.close();self.app.close()
        self.app=Application(self.config);await self.app.start()
        identity=self.app.registry.authenticate('alice',self.alice['token'])
        restored=await self.app.session(identity=identity)
        self.assertEqual(restored.account.uid,a.uid)
        self.assertEqual(restored.account.get_reward_balances()['ed'],123)
        self.assertEqual(len([i for i in restored.account.get_inventory_snapshot()['items'] if i['template']==77000]),1)

    async def test_duplicate_login_and_disconnect_release(self):
        first,second=await asyncio.gather(self.peer(self.alice),self.peer(self.alice))
        await asyncio.gather(first.roster(),second.roster())
        uid=self.app.accounts[self.alice['id']].uid
        for peer in (first,second):await peer.send(0x490);await peer.until(0x491)
        await first.send(0x28,struct.pack('>Q',uid));await first.until(0x29)
        await second.send(0x28,struct.pack('>Q',uid))
        self.assertEqual(await asyncio.wait_for(second.reader.read(),5),b'')
        await first.close()
        for _ in range(100):
            if self.alice['id'] not in self.app.playing:break
            await asyncio.sleep(.01)
        self.assertNotIn(self.alice['id'],self.app.playing)
        reconnect=await self.peer(self.alice);await reconnect.roster()
        await reconnect.send(0x490);await reconnect.until(0x491)
        await reconnect.send(0x28,struct.pack('>Q',uid));await reconnect.until(0x29)
        self.app.registry.disable('alice')
        with self.assertRaisesRegex(ValueError,'authentication'):await self.bridge(self.alice).remote()
        # Revocation also closes already authenticated sessions on their next request.
        try:await reconnect.send(0x48d)
        except ConnectionError:pass  # Periodic revocation may already close it.
        async with asyncio.timeout(5):
            try:
                while await reconnect.reader.read(65536):pass
            except ConnectionError:pass

    async def test_local_bridge_and_udp_account_scope(self):
        def free_port():
            with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
        # Server and bridge must agree on the fixed native UDP port.
        bridge=self.bridge(self.bob,local_port=free_port())
        await bridge.start()
        reader,writer=await asyncio.open_connection('127.0.0.1',bridge.config.local_port)
        try:
            welcome=decode_event(decode_frame(await read_wire(reader),BOOTSTRAP_KEYS).plaintext)
            self.assertIsNotNone(read_welcome(welcome))
            from els_server.port_probe import probe_reply
            probe=b'\x15'+struct.pack('<QIH',self.bob['id'],0,0)
            self.assertIsNotNone(probe_reply(probe,('127.0.0.1',12345),bridge.account_ids))
            self.assertIsNone(probe_reply(b'\x15'+struct.pack('<QIH',self.alice['id'],0,0),('127.0.0.1',12345),bridge.account_ids))
            self.assertIsNone(probe_reply(probe,('192.0.2.1',12345),bridge.account_ids))
        finally:writer.close();await writer.wait_closed()

    async def test_creation_capacity_and_receipts_are_account_scoped(self):
        alice=Characters(self.config.state_file,self.alice['id'])
        bob=Characters(self.config.state_file,self.bob['id'])
        base=int(time.time())
        for number in range(16):
            with patch('els_server.storage.character_lifecycle.current_time',return_value=base+(number//4)*86400):
                alice.create('Alice'+str(number),1,'alice-create:'+str(number))
                if number==3:
                    with self.assertRaisesRegex(ValueError,'Daily character creation limit'):
                        alice.create('AliceDaily',1,'alice-daily')
        self.assertEqual(len(alice.list()),16)
        with patch('els_server.storage.character_lifecycle.current_time',return_value=base+4*86400):
            with self.assertRaisesRegex(ValueError,'capacity'):alice.create('AliceFull',1,'alice-full')
        # Bob can still create after the shared database has more than sixteen roles.
        own=bob.create('BobFirst',2,'bob-first')
        self.assertEqual(bob.create('BobFirst',2,'bob-first')['uid'],own['uid'])
        with self.assertRaisesRegex(ValueError,'another account'):alice.create('BobFirst',2,'bob-first')
        self.assertEqual(len(bob.list()),1)
        self.assertEqual(len(Characters(self.config.state_file).list()),1)

    async def test_import_uses_separate_copy_and_preserves_source(self):
        from tools.import_friends_save import copy_save
        from contextlib import closing
        def dump(path):
            with closing(sqlite3.connect(path)) as db:return '\n'.join(db.iterdump())
        before=dump(self.config.state_file)
        target=self.root/'imported.sqlite3'
        result=copy_save(self.config.state_file,target,self.alice['id'])
        self.assertEqual(result['characters'],1)
        self.assertEqual(dump(self.config.state_file),before)
        self.assertEqual(Characters(target,self.alice['id']).get(1001)['uid'],1001)
        snapshot=dump(target)
        with self.assertRaises(ValueError):copy_save(self.config.state_file,target,self.bob['id'])
        self.assertEqual(dump(target),snapshot)
        rejected=self.root/'rejected.sqlite3'
        with self.assertRaises(ValueError):copy_save(target,rejected,self.bob['id'])
        self.assertFalse(rejected.exists())


if __name__=='__main__':unittest.main()
