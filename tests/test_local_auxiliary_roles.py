"""LOCAL selection creates child LocalAccount objects for non-default roles."""
import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.storage.local_state import LocalState
from els_server.protocol.protocol_codec import Event


@unittest.skipUnless('local_auxiliary_noop' in LocalSession.handle.__code__.co_names,'LOCAL profile only')
class LocalRoleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        self.app=Application(ServerConfig(profile='bootstrap'));self.addCleanup(self.app.close)
        self.root=LocalAccount(LocalState(Path(self.temp.name)/'own.sqlite3'));self.root.enable_characters();self.app.account=self.root
        role=self.root.characters.create('SecondRole',1,'owned-local-second')
        self.child=self.root.for_character(role['uid'])
        self.session=await self.app.session();self.session.account=self.child
        self.session.role='game';self.session.phase='town_ready';self.session.client_build='dx11_260923'
        self.event=Event(0x202,kind=0x7d0,payload=bytes(9),performers=(0,))

    async def test_owned_selected_child_uses_fast_path(self):
        self.assertIsNot(self.child,self.app.account)
        self.assertIs(self.child.root,self.app.account)
        with patch.object(self.session,'expiration_notifications',side_effect=RuntimeError('ordinary route')):
            self.assertEqual(await self.app.call(self.session.handle,self.event),[])

    async def test_foreign_root_or_removed_cache_entry_does_not_borrow_binding(self):
        self.root.character_accounts.pop(self.child.uid)
        with patch.object(self.session,'expiration_notifications',side_effect=RuntimeError('ordinary route')):
            with self.assertRaisesRegex(RuntimeError,'ordinary route'):self.session.handle(self.event)
        foreign=LocalAccount(LocalState(self.root.store.path));foreign.enable_characters()
        self.session.account=foreign.for_character(self.child.uid)
        with patch.object(self.session,'expiration_notifications',side_effect=RuntimeError('ordinary route')):
            with self.assertRaisesRegex(RuntimeError,'ordinary route'):self.session.handle(self.event)


if __name__=='__main__':unittest.main()
