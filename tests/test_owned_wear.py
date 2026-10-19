"""Owned native104/105 regression; disposable SQL, no game or player saves."""
import sqlite3,struct,tempfile,unittest,uuid
from pathlib import Path
from contextlib import closing
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.characters import BASE_CLASSES
from els_server.storage.inventory_state import load_items
from els_server.storage.wear_moves import move

class OwnedWearTests(unittest.TestCase):
 def test_all_families_minime_retry_and_rollback(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'qa.sqlite3';account=LocalAccount(LocalState(path));account.enable_characters();connection=str(uuid.uuid4());sequence=0
   with closing(sqlite3.connect(path)) as db,db:db.execute('INSERT INTO inventory_items VALUES (910001,1001,30577,0,1,2,0)')
   def snapshot():
    with closing(sqlite3.connect(path)) as db:return load_items(db,1001)
   def send(a,b,seq=None,validate=lambda:None):
    nonlocal sequence
    sequence+=1
    return move(path,struct.pack('>BiBiB',*a,*b,0),1001,account_id=1,session_id=connection,sequence=sequence if seq is None else seq,validate=validate)
   original=snapshot()
   for family,cls in BASE_CLASSES.items():
    with self.subTest(family=family):
     with closing(sqlite3.connect(path)) as db,db:db.execute('UPDATE characters SET unit_type=?,unit_class=?,level=99 WHERE uid=1001',(family,cls))
     ack=send((2,0),(9,37));self.assertEqual(ack[-4:],bytes(4));first_seq=sequence
     self.assertEqual(next(i for i in snapshot() if i['uid']==910001)['slot'],37)
     send((9,37),(2,0));before=snapshot();send((2,0),(9,37),seq=first_seq);self.assertEqual(snapshot(),before)
     if family==10:
      send((2,0),(9,38));send((9,38),(9,37));send((9,37),(2,0))
     else:
      with self.assertRaises(ValueError):send((2,0),(9,38))
     self.assertEqual(snapshot(),original)
   with closing(sqlite3.connect(path)) as db,db:db.execute("CREATE TRIGGER fail_owned_wear BEFORE INSERT ON wear_move_receipts BEGIN SELECT RAISE(ABORT,'fixture SQL rollback'); END")
   with self.assertRaises(sqlite3.IntegrityError):send((2,0),(9,37))
   self.assertEqual(snapshot(),original)

if __name__=='__main__':unittest.main()
