import sqlite3,struct,tempfile,unittest
from contextlib import closing
from pathlib import Path
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.manufacture_preflight import inspect
from els_server.storage.profession_state import replace
from els_server.protocol.profession_messages import ProfessionState


class ManufacturePreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'save.db'
        self.account=LocalAccount(LocalState(self.path));self.account.enable_characters()

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db:return list(db.iterdump())

    def test_read_only_legacy_snapshot_and_no_file_creation(self):
        before=self.dump()
        result=inspect(self.path,1001,1,struct.pack('>iiqI',30445,1,-1,0),now=2000000000)
        self.assertEqual(result['owner'],1001)
        self.assertEqual(result['observed_revisions']['profession'],0)
        self.assertFalse(result['transaction_implemented'])
        self.assertFalse(result['fee_waivers_verified'])
        self.assertEqual(before,self.dump())
        missing=self.path.with_name('missing.db')
        with self.assertRaises(sqlite3.OperationalError):
            inspect(missing,1001,1,b'',now=0)
        self.assertFalse(missing.exists())

    def test_account_and_character_inventory_isolation(self):
        other=self.account.characters.create('CraftOther',5,'craft-other')
        with closing(sqlite3.connect(self.path)) as db:
            other_item=db.execute('SELECT uid FROM inventory_items WHERE owner=? LIMIT 1',
                                  (other['uid'],)).fetchone()[0]
        before=self.dump()
        for owner,account in ((1001,2),(9999,1),(True,1),(1001,True)):
            with self.subTest(owner=owner,account=account),self.assertRaises(ValueError):
                inspect(self.path,owner,account,struct.pack('>iiqI',30445,1,-1,0),now=2000000000)
        with self.assertRaisesRegex(ValueError,'missing or unavailable'):
            inspect(self.path,1001,1,struct.pack('>iiqI',30445,1,other_item,0),now=2000000000)
        self.assertEqual(before,self.dump())

    def test_saved_profession_is_used_and_reopened_without_writes(self):
        payload=struct.pack('>iiqI',10078906,1,-1,0)
        before=self.dump()
        with self.assertRaisesRegex(ValueError,'profession requirement'):
            inspect(self.path,1001,1,payload,now=2000000000)
        self.assertEqual(before,self.dump())
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            replace(db,1001,1,0,ProfessionState(profession=3,level=8))
        before=self.dump()
        result=inspect(self.path,1001,1,payload,now=2000000000)
        self.assertTrue(result['profession']['satisfied'])
        self.assertEqual(result['observed_revisions']['profession'],1)
        self.assertEqual(before,self.dump())

    def test_concurrent_commit_does_not_mix_snapshot_balances(self):
        from unittest.mock import patch
        from els_server.storage.inventory_state import load_items
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('PRAGMA journal_mode=WAL')
            old_ed=db.execute('SELECT ed FROM reward_balances WHERE uid=1001').fetchone()[0]
        def load_while_other_writer_commits(db,owner):
            with closing(sqlite3.connect(self.path)) as writer,writer:
                writer.execute('UPDATE reward_balances SET ed=ed+100,revision=revision+1 WHERE uid=1001')
            return load_items(db,owner)
        with patch('els_server.storage.manufacture_preflight.load_items',side_effect=load_while_other_writer_commits):
            result=inspect(self.path,1001,1,struct.pack('>iiqI',30445,1,-1,0),now=2000000000)
        self.assertEqual(result['available_ed'],old_ed)
        reopened=inspect(self.path,1001,1,struct.pack('>iiqI',30445,1,-1,0),now=2000000000)
        self.assertEqual(reopened['available_ed'],old_ed+100)


if __name__=='__main__':unittest.main()
