"""Fresh accounts create their own named characters over real TLS/native frames."""
import sqlite3,struct,unittest
from contextlib import closing
import test_friends_server as native
import test_registration as registration
from els_server.protocol.local_messages import i32,wstring
from els_server.protocol.character_messages import NAME_TAKEN,NAME_INVALID,NAME_LENGTH
from els_server.storage.characters import Characters,BASE_CLASSES
from els_server.domain.local_session import SessionOrderError
from dataclasses import replace


class CharacterCreationTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=native.FriendsTests.asyncSetUp
    asyncTearDown=native.FriendsTests.asyncTearDown
    bridge=native.FriendsTests.bridge
    request=registration.RegistrationTests.request

    async def peer(self,identity):
        peer=await native.Peer.open(self.bridge(identity));self.peers.append(peer)
        return peer

    async def create(self,peer,name,unit_type):
        await peer.send(0x489,wstring(name)+struct.pack('>iiBBI',BASE_CLASSES[unit_type],1,0,0,0))
        return await peer.until(0x25)

    async def name(self,peer,name):
        await peer.send(0x48b,i32(1)+wstring(name))
        return struct.unpack_from('>i',(await peer.until(0x48c)).payload)[0]

    def count(self):
        with closing(sqlite3.connect(self.config.state_file)) as db:
            return dict((table,db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0])
                        for table in ('characters','character_owners','location','reward_balances','inventory_items','character_creation_receipts'))

    async def test_registration_first_login_empty_then_create_select_and_reconnect(self):
        self.server.config=replace(self.config,registration_enabled=True)
        self.server.account_gateway.config=self.server.config
        before=self.count()
        login=await self.request(dict(op='register',name='brandnew',password='StrongPass123'))
        self.assertTrue(login['ok'])
        peer=await self.peer(login)
        roster=await peer.roster()
        self.assertEqual(struct.unpack_from('>I',roster.payload,24)[0],0)
        self.assertEqual(self.count(),before)
        account=self.app.accounts[self.app.registry.authenticate(login['name'],login['token'])['id']]
        self.assertIsNone(account.uid);self.assertIsNone(account.character())
        with self.assertRaisesRegex(SessionOrderError,'No character'):account.get_inventory_snapshot()
        with self.assertRaises(ValueError):account.for_character(1001)
        self.assertEqual(await self.name(peer,'星光伊芙'),0)
        reply=await self.create(peer,'星光伊芙',5)
        self.assertEqual(reply.payload[:4],bytes(4))
        role=account.characters.list()[0]
        self.assertEqual((role['name'],role['unit_type']),('星光伊芙',5))
        await peer.enter_town(role['uid'])
        self.assertEqual(self.app.playing[account.account_id].account.character()['name'],'星光伊芙')
        await peer.close()
        async with native.asyncio.timeout(5):
            while self.app.playing:await native.asyncio.sleep(.02)
        peer=await self.peer(login);roster=await peer.roster()
        self.assertEqual(struct.unpack_from('>I',roster.payload,24)[0],1)
        self.assertIn('星光伊芙'.encode('utf-16le'),roster.payload)
        await peer.enter_town(role['uid'])
        self.assertEqual(len(account.characters.list()),1)

    async def test_duplicate_invalid_names_and_both_roster_phases(self):
        alice=await self.peer(self.alice);bob=await self.peer(self.bob)
        await alice.roster();await bob.roster()
        # Name in the screenshot is a global duplicate, including case folding.
        self.assertEqual((await self.create(alice,'Deemo',5)).payload[:4],bytes(4))
        before=self.count()
        self.assertEqual(await self.name(bob,'Deemo'),NAME_TAKEN)
        self.assertEqual(await self.name(bob,'deemo'),NAME_TAKEN)
        self.assertEqual(struct.unpack_from('>i',(await self.create(bob,'Deemo',5)).payload)[0],NAME_TAKEN)
        for value,code in (('a',NAME_LENGTH),('a'*13,NAME_LENGTH),('bad name',NAME_INVALID),('a!',NAME_INVALID)):
            self.assertEqual(await self.name(bob,value),code)
            self.assertEqual(struct.unpack_from('>i',(await self.create(bob,value,5)).payload)[0],code)
        self.assertEqual(self.count(),before)
        await bob.send(0x490);await bob.until(0x491)
        self.assertEqual(await self.name(bob,'朋友伊芙'),0)
        self.assertEqual((await self.create(bob,'朋友伊芙',5)).payload[:4],bytes(4))
        self.assertEqual([c['name'] for c in Characters(self.config.state_file,self.bob['id']).list()],['朋友伊芙'])

    async def test_all_fifteen_character_types_and_existing_role_preserved(self):
        old=Characters(self.config.state_file,self.alice['id']).create('Player8',1,'existing-save')
        peer=await self.peer(self.alice);await peer.roster()
        self.assertEqual(self.app.accounts[self.alice['id']].uid,old['uid'])
        fresh=await self.peer(self.bob);await fresh.roster()
        for unit_type in BASE_CLASSES:
            name='自建角色'+str(unit_type)
            self.assertEqual(await self.name(fresh,name),0)
            self.assertEqual((await self.create(fresh,name,unit_type)).payload[:4],bytes(4))
        rows=Characters(self.config.state_file,self.bob['id']).list()
        self.assertEqual([c['unit_type'] for c in rows],list(BASE_CLASSES))
        self.assertEqual(Characters(self.config.state_file,self.alice['id']).get(old['uid']),old)


if __name__=='__main__':unittest.main()
