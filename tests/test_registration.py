"""Real pinned TLS registration/login plus legacy-token compatibility."""
import asyncio,json,sqlite3,struct,sys,unittest
from dataclasses import replace
from contextlib import closing
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
import test_friends_server as native_tests
from els_server.friends_wire import read_json,write_json
from els_server.storage.accounts import Accounts


class RegistrationTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=native_tests.FriendsTests.asyncSetUp
    asyncTearDown=native_tests.FriendsTests.asyncTearDown
    bridge=native_tests.FriendsTests.bridge
    peer=native_tests.FriendsTests.peer

    async def request(self,document):
        import ssl,hashlib
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);context.check_hostname=False;context.verify_mode=ssl.CERT_NONE
        r,w=await asyncio.open_connection('127.0.0.1',self.port,ssl=context)
        try:
            self.assertEqual(hashlib.sha256(w.get_extra_info('ssl_object').getpeercert(binary_form=True)).hexdigest(),self.pin)
            await write_json(w,document);reply=await read_json(r)
            self.assertEqual(await r.read(),b'')
            return reply
        finally:w.close();await w.wait_closed()

    async def test_register_login_session_and_legacy_accounts(self):
        self.server.config=replace(self.config,registration_enabled=True)
        self.server.account_gateway.config=self.server.config
        self.assertTrue((await self.request({'op':'status'}))['registration_enabled'])
        body=dict(op='register',name='test_friend',password='朋友StrongPass123')
        result=await self.request(body);self.assertTrue(result['ok'])
        self.assertEqual((await self.request(body))['error'],'name_taken')
        wrong=await self.request(dict(body,op='login',password='wrong_pass'))
        self.assertEqual(wrong['error'],'bad_credentials')
        login=await self.request(dict(body,op='login'));self.assertTrue(login['ok'])
        self.assertNotEqual(result['token'],login['token'])
        self.assertTrue((await self.request(dict(op='resume',name=login['name'],token=login['token'])))['ok'])
        peer=await self.peer(dict(name=login['name'],token=login['token']))
        await peer.roster()
        old=await self.peer(self.alice);await old.roster()
        self.app.registry.disable(login['name'])
        self.assertFalse((await self.request(dict(body,op='login')))['ok'])
        with self.assertRaises(ValueError):self.app.registry.authenticate(login['name'],login['token'])
        data=json.dumps(self.events)
        self.assertNotIn(body['password'],data);self.assertNotIn(login['token'],data)
        with closing(sqlite3.connect(self.config.accounts_file)) as db:
            dump='\n'.join(db.iterdump())
        self.assertNotIn(body['password'],dump);self.assertNotIn(login['token'],dump)

    async def test_closed_invalid_fields_and_rate_limit(self):
        self.assertEqual((await self.request(dict(op='register',name='newuser',password='password123')))['error'],'registration_closed')
        self.assertFalse((await self.request(dict(op='login',name='alice',password='password123',admin=True)))['ok'])
        for _ in range(12):await self.request(dict(op='login',name='alice',password='password123'))
        self.assertEqual((await self.request(dict(op='login',name='alice',password='password123')))['error'],'rate_limited')

    async def test_password_bounds_account_cap_and_expired_session(self):
        registry=self.app.registry
        for value in ('short','x'*65,'a'*8+'\n'):
            with self.assertRaises(ValueError):registry.register('newuser',value)
        with self.assertRaisesRegex(ValueError,'registration_full'):registry.register('newuser','password123',2)
        result=registry.register('newuser','password123')
        with closing(sqlite3.connect(self.config.accounts_file)) as db,db:db.execute('UPDATE account_sessions SET expires=0')
        with self.assertRaises(ValueError):registry.authenticate('newuser',result['token'])
        with self.assertRaises(ValueError):registry.password_login('owner','password123')


if __name__=='__main__':unittest.main()
