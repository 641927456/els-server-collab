"""Portable wishlist transaction regressions; no image, network or game."""
import sqlite3,tempfile,unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage import wishlist_state as store
from els_server.domain import fashion_singles

class FiniteAccountWishlist(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='wishlist-git-context-');self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'private.sqlite3'
        a=LocalAccount(LocalState(self.path),2);a.enable_characters()
        self.uid=a.characters.create('WishlistOne',1,'wishlist-portable-a')['uid']
        self.other=a.characters.create('WishlistTwo',2,'wishlist-portable-b')['uid']
        b=LocalAccount(LocalState(self.path),3);b.enable_characters()
        self.foreign=b.characters.create('WishThree',1,'wishlist-portable-c')['uid']
    def snapshot(self,account,uid):return store.snapshot(self.path,account,uid,lambda rows:rows)
    def change(self,account,uid,delete=False,encode=None):
        return store.modify(self.path,account,uid,(723522,),delete,encode or(lambda rows,delete:(rows,delete)))
    def test_account_projection_isolation_and_encoder_rollback(self):
        def failed_encode(*args):raise ValueError('private encoding fault')
        with self.assertRaises(ValueError):self.change(2,self.uid,encode=failed_encode)
        with closing(sqlite3.connect(self.path))as db:
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='account_wishlist_items'").fetchone())
        self.assertEqual(self.change(2,self.uid),((723522,),False))
        self.assertEqual(self.snapshot(2,self.uid),(723522,))
        self.assertEqual(self.snapshot(2,self.other),())
        self.assertEqual(self.snapshot(3,self.foreign),())
        with self.assertRaises(ValueError):self.change(3,self.uid)
        self.assertEqual(self.snapshot(2,self.uid),(723522,))
        with self.assertRaises(ValueError):self.change(2,self.uid,True,failed_encode)
        self.assertEqual(self.snapshot(2,self.uid),(723522,))
    def test_first_cold_delete_loads_source_before_write_lock(self):
        self.change(2,self.uid)
        fashion_singles.definitions.cache_clear();store.admitted.cache_clear();store._visible_templates.cache_clear()
        original=fashion_singles.definitions;observed=[]
        def inspect_source_load():
            with closing(sqlite3.connect(self.path,timeout=0))as peer:
                peer.execute('BEGIN IMMEDIATE');peer.rollback()
            observed.append(True);return original()
        with patch.object(fashion_singles,'definitions',inspect_source_load):
            self.assertEqual(self.change(2,self.uid,True),((723522,),True))
        self.assertEqual(observed,[True]);self.assertEqual(self.snapshot(2,self.uid),())

if __name__=='__main__':unittest.main()
