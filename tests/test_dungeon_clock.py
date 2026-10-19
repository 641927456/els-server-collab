"""Active-stage clock, real C1 fields, atomic BEST and replay isolation."""
import sqlite3,struct,sys,tempfile,uuid
from contextlib import closing
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from els_server.domain.dungeon_clock import DungeonClock
from els_server.storage.reward_state import RewardState,RewardConflict
from els_server.domain.dungeon_clear import reward_clear_notice

t=[100.0];clock=DungeonClock(lambda:t[0])
assert clock.seconds()==0
clock.resume();t[0]+=12.75;clock.resume();clock.pause()
t[0]+=60;assert clock.seconds()==12
clock.pause();clock.resume();t[0]+=20.5;clock.pause()
assert clock.seconds()==33
def builder(seconds):
 return lambda balances,best:reward_clear_notice(120,50,elapsed_seconds=seconds,best_seconds=best).payload
def times(reply):return struct.unpack_from('>i',reply['response'],0)[0],struct.unpack_from('>i',reply['response'],460)[0]
with tempfile.TemporaryDirectory() as d:
 path=Path(d)/'test.db';store=RewardState(path)
 def grant(seconds,run=None):return store.grant(run or str(uuid.uuid4()),b'verified clear',120,50,builder(seconds),dungeon_clear=(30000,seconds))
 run=str(uuid.uuid4());first=grant(83,run);assert times(first)==(83,83)
 assert times(grant(95))==(95,83)
 assert times(grant(61))==(61,61)
 retry=grant(83,run);assert retry['replayed'] and retry['response']==first['response']
 assert times(grant(0))==(0,61)
 with closing(sqlite3.connect(path)) as db,db:db.execute("CREATE TRIGGER fail_receipt BEFORE INSERT ON reward_receipts BEGIN SELECT RAISE(ABORT,'test'); END")
 before=store.balances()
 try:grant(20)
 except sqlite3.IntegrityError:pass
 else:raise AssertionError('Expected receipt failure')
 assert store.balances()==before
 with closing(sqlite3.connect(path)) as db,db:
  assert db.execute('SELECT seconds FROM dungeon_records').fetchone()==(61,)
  db.execute('DROP TRIGGER fail_receipt')
 other=RewardState(path,uid=1002)
 assert times(other.grant(str(uuid.uuid4()),b'other character',120,50,builder(90),dungeon_clear=(30000,90)))==(90,90)
 try:grant(82,run)
 except RewardConflict:pass
 else:raise AssertionError('Changed elapsed time replay accepted')
print('PASS: active time excludes loading, elapsed/BEST fields, per-character BEST, atomic rollback, immutable replay.')
