import asyncio
from dataclasses import replace
import ssl
import secrets
import unittest
from test_friends_server import FriendsTests
from els_server.friends_wire import read_json,write_json


class ArchitectureTLS(FriendsTests):
    async def api(self,document):
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname=False;context.verify_mode=ssl.CERT_NONE
        reader,writer=await asyncio.open_connection('127.0.0.1',self.port,ssl=context)
        try:
            await write_json(writer,document)
            return await read_json(reader)
        finally:writer.close();await writer.wait_closed()

    async def test_wire_registration_login_resume_and_live_revocation(self):
        self.server.account_gateway.config=replace(self.config,registration_enabled=True)
        password=secrets.token_urlsafe(24)
        created=await self.api(dict(op='register',name='qa_wire_new',password=password))
        self.assertTrue(created['ok'])
        logged=await self.api(dict(op='login',name='qa_wire_new',password=password))
        self.assertTrue(logged['ok']);self.assertEqual(created['account_id'],logged['account_id'])
        resumed=await self.api(dict(op='resume',name='qa_wire_new',token=logged['token']))
        self.assertTrue(resumed['ok'])
        self.app.registry.disable('qa_wire_new')
        denied=await self.api(dict(op='login',name='qa_wire_new',password=password))
        self.assertEqual(denied['error'],'bad_credentials')
        self.assertEqual(self.app.preparation.snapshot()['completed'],3)
        self.assertFalse(any(e['event']=='worker_error' for e in self.events))


def load_tests(loader,tests,pattern):
    return unittest.TestSuite([ArchitectureTLS('test_wire_registration_login_resume_and_live_revocation')])
