"""Default mount tail stays byte-identical; experimental level/exp slots roundtrip."""
import sqlite3,struct,sys,tempfile,unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from els_server.protocol import mount_messages
from els_server.storage import mount_progress

ZERO_TAIL=struct.pack('>QHBiI',0,0,0,0,0)
MOUNT=dict(uid=7,unit=85,name='Ghost',stamina=120,native_time1=1,accounted_at=2,ridden=True,no_stamina=False)

class MountLevelProbeTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'probe.sqlite3'
  with closing(sqlite3.connect(self.path)) as db,db:mount_progress.ensure(db)
 def test_default_payload_is_byte_identical(self):
  with patch.object(mount_messages,'LEVEL_SLOT','h'):
   plain=mount_messages.record(MOUNT)
   self.assertEqual(plain[-19:],ZERO_TAIL);self.assertEqual(mount_messages.record(dict(MOUNT,level=0,exp=0)),plain)
   self.assertEqual(mount_messages.record(None)[-19:],ZERO_TAIL)
 def test_h_slot_holds_level_and_q_holds_exp(self):
  with patch.object(mount_messages,'LEVEL_SLOT','h'):
   tail=mount_messages.tail_fields(dict(MOUNT,level=1))
   self.assertEqual(tail,struct.pack('>QHBiI',0,1,0,0,0))
   self.assertEqual(mount_messages.tail_fields(dict(MOUNT,level=1,exp=5)),struct.pack('>QHBiI',5,1,0,0,0))
 def test_q_slot_holds_level(self):
  with patch.object(mount_messages,'LEVEL_SLOT','q'):
   self.assertEqual(mount_messages.tail_fields(dict(MOUNT,level=1)),struct.pack('>QHBiI',1,0,0,0,0))
 def test_progress_roundtrip(self):
  with closing(sqlite3.connect(self.path)) as db,db:
   self.assertEqual(mount_progress.load(db,7),{'level':0,'exp':0,'slot':'h'})
   mount_progress.set_level(db,7,1)
   self.assertEqual(mount_progress.load(db,7),{'level':1,'exp':0,'slot':'h'})
   mount_progress.set_level(db,7,3,42)
   self.assertEqual(mount_progress.load(db,7),{'level':3,'exp':42,'slot':'h'})
   mount_progress.set_level(db,7,3,42,'q')
   self.assertEqual(mount_progress.load(db,7),{'level':3,'exp':42,'slot':'q'})
   self.assertEqual(mount_messages.tail_fields(dict(MOUNT,level=3,exp=42,slot='q')),struct.pack('>QHBiI',3,0,0,0,0))
   mount_progress.clear(db,7)
   self.assertEqual(mount_progress.load(db,7),{'level':0,'exp':0,'slot':'h'})
   self.assertEqual([r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")],['mount_progress'])
 def test_load_without_table_reads_zero(self):
  path=Path(self.temp.name)/'empty.sqlite3';sqlite3.connect(path).close()
  with closing(sqlite3.connect(path)) as db:
   self.assertEqual(mount_progress.load(db,7),{'level':0,'exp':0,'slot':'h'})
   self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(),[])

if __name__=='__main__':unittest.main()
