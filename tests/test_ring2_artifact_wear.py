"""Disposable save regression for second-ring and Artifact frame retries."""
import sqlite3,struct,tempfile,unittest,uuid
from pathlib import Path
from contextlib import closing
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import load_items
from els_server.storage.wear_moves import move
from els_server.storage.artifact_progression import move as artifact_move

class RingArtifactWearTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'qa.sqlite3';self.a=LocalAccount(LocalState(self.path));self.a.enable_characters();self.session=str(uuid.uuid4());self.sequence=0
 def snapshot(self):
  with closing(sqlite3.connect(self.path)) as db:return load_items(db,1001)
 def send(self,source,dest,artifact=False,sequence=None,validate=lambda:None):
  self.sequence+=1
  return (artifact_move if artifact else move)(self.path,struct.pack('>BiBiB',*source,*dest,0),1001,account_id=1,session_id=self.session,sequence=self.sequence if sequence is None else sequence,validate=validate)
 def test_second_ring_swap_retry_cannot_move_replacement(self):
  with closing(sqlite3.connect(self.path)) as db,db:
   db.execute('INSERT INTO inventory_items VALUES (910001,1001,92112,0,1,2,0)');db.execute('INSERT INTO inventory_items VALUES (910002,1001,92112,0,1,2,1)')
  self.send((2,0),(9,17));self.send((2,1),(9,41));self.send((9,17),(9,41));frame=self.sequence
  self.send((9,17),(2,0));after=self.snapshot();self.send((9,17),(9,41),sequence=frame);self.assertEqual(self.snapshot(),after)
  with self.assertRaises(ValueError):self.send((2,0),(9,41),sequence=frame)
  self.assertEqual(self.snapshot(),after)
 def test_nondefault_artifact_swap_retains_children_and_replay_state(self):
  from els_server.domain.artifact_identification import identify_values
  from els_server.storage.equipment_options import replace as options
  from els_server.storage.artifact_equipment_state import replace as socket
  with closing(sqlite3.connect(self.path)) as db,db:
   db.execute('BEGIN IMMEDIATE');db.execute('UPDATE characters SET unit_class=79,level=99,transcendence=1,master=1 WHERE uid=1001');db.execute("INSERT OR REPLACE INTO character_artifacts VALUES (1001,1,1,1,0,'[0,0,0,0]')")
   for n,t in enumerate((168603,168918)):
    uid=920001+n;db.execute('INSERT INTO inventory_items VALUES (?,1001,?,0,1,1,?)',(uid,t,n));groups={'1':identify_values(t,[],lambda limit:0)}
    if n:groups['31']=[710000,710010,710020]
    options(db,1001,uid,{},groups);socket(db,1001,uid,False,True)
  original=self.snapshot();self.send((1,0),(24,3),True);self.send((1,1),(24,4),True);self.send((24,3),(24,4),True);frame=self.sequence;after=self.snapshot()
  self.send((24,3),(24,4),True,sequence=frame);self.assertEqual(self.snapshot(),after)
  self.send((24,3),(1,1),True);after=self.snapshot();self.send((24,3),(24,4),True,sequence=frame);self.assertEqual(self.snapshot(),after)
  self.send((24,4),(1,0),True);self.assertEqual(self.snapshot(),original)
  calls=0
  def stale():
   nonlocal calls
   calls+=1
   if calls==3:raise ValueError('stale actor before commit')
  with self.assertRaises(ValueError):self.send((1,0),(24,3),True,validate=stale)
  self.assertEqual(self.snapshot(),original)
if __name__=='__main__':unittest.main()
