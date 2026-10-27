"""Current native mount retries must agree with the authoritative ride state."""
import sqlite3,struct,sys,tempfile,unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

# Requires the repository's SHA-locked runtime assets; see docs/TESTING.md.
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items
from els_server.domain.inventory_items import VERIFIED_TEMPLATES
from els_server.storage.companion_state import handle as activate,snapshot
from els_server.storage.mount_state import handle
from els_server.domain.mount_flow import handle as flow
from els_server.protocol.protocol_codec import Event

class MountRetryTests(unittest.TestCase):
    def setUp(self):
        self.clock=patch('els_server.storage.mount_state.time.time',return_value=1000);self.clock.start();self.addCleanup(self.clock.stop)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'save.sqlite3'
        self.account=LocalAccount(LocalState(self.path));self.account.enable_characters();self.account.get_inventory_snapshot()
        with closing(sqlite3.connect(self.path))as db,db:
            items=grant_items(db,[dict(template=550431,metadata=VERIFIED_TEMPLATES[550431],group=4,quantity=2)])
        for n,item in enumerate(items):activate(self.path,1001,0x432,struct.pack('>Q',item['uid']),'activate'+str(n))
        self.mounts=[p for p in snapshot(self.path,1001)['companions']if p['kind']=='mount']
        self.uid=self.mounts[0]['uid'];self.other=self.mounts[1]['uid']
    def ride(self,operation,uid=None,now=1000):
        return handle(self.path,1001,0x42c,struct.pack('>QB',uid or self.uid,1),operation,now=now)
    def down(self,operation='down',now=1010):
        return handle(self.path,1001,0x42f,struct.pack('>Qi',self.uid,0),operation,now=now)
    def rows(self):
        with closing(sqlite3.connect(self.path))as db:
            return {table:db.execute('SELECT * FROM '+table+' ORDER BY 1,2').fetchall()
                    for table in ('companions','companion_active','mount_runtime','mount_operations','inventory_items','reward_balances')}
    def sequence(self):
        self.ride('ride');self.down();self.ride('ride-later',now=1020)
    def test_superseded_down_same_mount_rejected_without_sql_change(self):
        self.sequence();before=self.rows()
        with self.assertRaisesRegex(ValueError,'Stale dismount retry'):self.down(now=1030)
        self.assertEqual(self.rows(),before)
    def test_superseded_down_other_mount_rejected_without_sql_change(self):
        self.ride('ride');self.down();self.ride('other',uid=self.other,now=1020);before=self.rows()
        with self.assertRaisesRegex(ValueError,'Stale dismount retry'):self.down(now=1030)
        self.assertEqual(self.rows(),before)
    def test_current_down_replay_remains_success_and_one_receipt(self):
        self.ride('ride');self.down();reply=self.down(now=1020)
        self.assertEqual(reply.kind,0x430);self.assertEqual(struct.unpack_from('>iQ',reply.payload),(0,self.uid))
        with closing(sqlite3.connect(self.path))as db:
            self.assertEqual(db.execute('SELECT mount,mounted FROM companion_active WHERE owner=1001').fetchone(),(0,0))
            self.assertEqual(db.execute('SELECT ridden FROM mount_runtime WHERE uid=?',(self.uid,)).fetchone(),(0,))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM mount_operations WHERE owner=1001 AND operation='down'").fetchone(),(1,))
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
    def test_flow_returns_native_failure_for_superseded_down(self):
        session=SimpleNamespace(item_test=True,client_build='dx11_260923',role='game',phase='town_ready',account=self.account,shop_session_id='own-native')
        def request(kind,sequence):return flow(session,Event(0x202,kind=kind,payload=struct.pack('>QB',self.uid,1)if kind==0x42c else struct.pack('>Qi',self.uid,0)),sequence)
        self.assertEqual(struct.unpack_from('>i',request(0x42c,1)[0].payload),(0,))
        self.assertEqual(struct.unpack_from('>i',request(0x42f,2)[0].payload),(0,))
        self.assertEqual(struct.unpack_from('>i',request(0x42c,3)[0].payload),(0,))
        before=self.rows();answer=request(0x42f,2)
        self.assertEqual([e.kind for e in answer],[0x430]);self.assertEqual(struct.unpack_from('>iQ',answer[0].payload),(-1,0))
        self.assertEqual(self.rows(),before)
    def test_conflicting_and_foreign_retry_remain_rejected(self):
        self.ride('ride');self.down();before=self.rows()
        with self.assertRaisesRegex(ValueError,'Conflicting riding retry'):self.ride('down',now=1020)
        with self.assertRaisesRegex(ValueError,'Owned mount required'):
            handle(self.path,1002,0x42f,struct.pack('>Qi',self.uid,0),'down',now=1020)
        self.assertEqual(self.rows(),before)

if __name__=='__main__':unittest.main(verbosity=2)
