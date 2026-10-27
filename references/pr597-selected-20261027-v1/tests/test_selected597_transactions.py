"""Real SQLite failures and concurrent repeat notifications for the new writer."""
import concurrent.futures, sqlite3, unittest
from contextlib import closing
from unittest.mock import patch
import test_mount_recall as fixture
from els_server.storage import mount_state

class RecallTransactions(unittest.TestCase):
    setUp=fixture.RecallTests.setUp
    ride=fixture.RecallTests.ride
    active=fixture.RecallTests.active
    saved=fixture.RecallTests.saved
    def dump(self):
        with closing(sqlite3.connect(self.path))as db:return list(db.iterdump())

    def test_failure_after_stamina_update_rolls_every_row_back(self):
        self.ride();before=self.dump();original=mount_state.settle
        def fail(db,*a,**kw):
            original(db,*a,**kw);raise ValueError('qualified injected failure after settlement')
        with patch.object(mount_state,'settle',side_effect=fail):
            with self.assertRaises(ValueError):mount_state.recall(self.path,1001,now=1024)
        self.assertEqual(self.dump(),before)
        mount_state.recall(self.path,1001,now=1024)
        self.assertEqual(self.active(),(0,0));self.assertAlmostEqual(self.saved(1024)[self.uid]['stamina'],110)

    def test_wrong_owner_and_unknown_owner_never_release_another_character(self):
        self.ride();before=self.dump()
        self.assertIsNone(mount_state.recall(self.path,1002,now=1024))
        self.assertEqual(self.dump(),before)
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('UPDATE mount_runtime SET owner=1002 WHERE uid=?',(self.uid,))
        before=self.dump()
        with self.assertRaises(ValueError):mount_state.recall(self.path,1001,now=1024)
        self.assertEqual(self.dump(),before)

    def test_eight_concurrent_releases_settle_one_interval_only(self):
        self.ride()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8)as pool:
            results=list(pool.map(lambda _:mount_state.recall(self.path,1001,now=1024),range(8)))
        self.assertEqual(sum(r is not None for r in results),1)
        self.assertEqual(self.active(),(0,0));self.assertAlmostEqual(self.saved(1024)[self.uid]['stamina'],110)

    def test_clock_rollback_does_not_recredit_previous_ridden_interval(self):
        self.ride();mount_state.recall(self.path,1001,now=900)
        self.assertAlmostEqual(self.saved(1000)[self.uid]['stamina'],120)
        self.assertEqual(self.active(),(0,0))
