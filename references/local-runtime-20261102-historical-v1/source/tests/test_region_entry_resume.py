"""Region entry resume walks the whole board-only chain one claim at a time."""
import sqlite3,json,struct,sys,tempfile,unittest
from contextlib import closing
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from els_server.domain.boosting_2026_region_entries import resume
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.seal_quests import ensure

CHAIN=(27540,27550,27560,27570,27580,27590,27600)

class RegionEntryResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'resume.db';self.a=LocalAccount(LocalState(self.path));self.a.enable_characters()
        with closing(sqlite3.connect(self.path)) as db,db:
            ensure(db)
            db.execute('UPDATE characters SET level=99 WHERE uid=?',(self.a.uid,))
            for qid in (26640,26650,26690):
                db.execute('INSERT INTO completed_quests VALUES(?,?,?,?)',(self.a.uid,qid,1000,'{}'))

    def resume(self,now=1800000000):
        with closing(sqlite3.connect(self.path,timeout=10)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            return resume(db,self.a.uid,self.a.account_id,now=now,
                location=('town',20013))

    def quests(self):
        with closing(sqlite3.connect(self.path,timeout=10)) as db:
            return db.execute('SELECT quest FROM character_quests WHERE owner=?',(self.a.uid,)).fetchall()

    def complete(self,qid):
        with closing(sqlite3.connect(self.path,timeout=10)) as db,db:
            db.execute('INSERT OR IGNORE INTO completed_quests VALUES(?,?,?,?)',(self.a.uid,qid,1000,'{}'))

    def test_whole_board_chain_in_native_order(self):
        for index,qid in enumerate(CHAIN):
            messages=self.resume(1800000000+index*3)
            self.assertEqual([e.kind for e in messages],[0xf0],qid)
            self.assertEqual(struct.unpack_from('>i',messages[0].payload)[0],qid)
            with closing(sqlite3.connect(self.path,timeout=10)) as db:
                row=db.execute('SELECT objectives FROM character_quests WHERE owner=? AND quest=?',(self.a.uid,qid)).fetchone()
            self.assertEqual(set(json.loads(row[0]).values()),{0})
            # Idempotent while the entry is still unfinished.
            self.assertEqual(self.resume(1800000000+index*3+1),[])
            self.complete(qid)
        self.assertEqual(self.resume(1800000200),[]) # 27600 is the last entry

    def test_non_participant_gets_nothing(self):
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE characters SET level=98 WHERE uid=?',(self.a.uid,))
        self.assertEqual(self.resume(),[])
        self.assertEqual(self.quests(),[])

if __name__=='__main__':unittest.main()
