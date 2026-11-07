"""Original notices/full SQL, failed encode rollback, real per-file FIFO turn."""
import runtime_fixture as h
import asyncio,concurrent.futures,contextlib,json,sqlite3,time
from unittest.mock import patch
from profile_town import seed
from els_server.domain import growth_guide_flow as guide
from els_server.storage import title_levels as titles
from els_server.storage.read_scope import committed_reads
from els_server.storage.sqlite_timing import _writer_turn
old_guide=h.load('own_original_cold_guide',h.BASE/'els_server/domain/growth_guide_flow.py')
old_titles=h.load('own_original_cold_titles',h.BASE/'els_server/storage/title_levels.py')
def dump(path):
 with contextlib.closing(sqlite3.connect(path))as db:return tuple(sorted(db.iterdump()))
async def main():
 c=h.f.FriendsTests();await c.asyncSetUp();checks=[]
 try:
  uid=seed(c,c.alice,'OwnColdSQL');p=await c.peer(c.alice);await p.roster();await p.enter_town(uid);await c.server.periodics.close();s=c.app.playing[c.alice['id']];path=c.config.state_file
  saved=dict(vars(s));before=dump(path)
  with committed_reads(connections=c.app.read_connections):expected=old_guide.synchronize(s,[],force=True)
  s.__dict__.clear();s.__dict__.update(saved)
  with committed_reads(connections=c.app.read_connections):actual=guide.synchronize(s,[],force=True)
  assert actual==expected and dump(path)==before;checks.append('growth original notices and whole SQL')
  def clone(label):
   out=c.root/(label+'.sqlite3')
   with contextlib.closing(sqlite3.connect(path))as src,contextlib.closing(sqlite3.connect(out))as db:src.backup(db)
   with contextlib.closing(sqlite3.connect(out))as db,db:db.execute("DELETE FROM title_ownership WHERE scope='character'AND subject=?",(uid,))
   return out
  a,b=clone('old-titles'),clone('new-titles');fixed=int(time.time())
  expected=old_titles.synchronize(a,uid,now=fixed)
  with committed_reads(connections=c.app.read_connections):actual=titles.synchronize(b,uid,now=fixed)
  assert actual==expected and dump(a)==dump(b);checks.append('level titles original positive result and whole SQL')
  failure=clone('failed-titles');before=dump(failure)
  def reject(*_):raise ValueError('Owned cold title encoding failure')
  try:
   with patch.object(titles,'_events',reject):titles.synchronize(failure,uid,now=fixed)
  except ValueError as error:assert str(error)=='Owned cold title encoding failure'
  else:raise AssertionError('Title encoding failure hidden')
  assert dump(failure)==before;checks.append('positive title encode failure rollback')
  queued=clone('queued-titles')
  with contextlib.closing(sqlite3.connect(queued))as db:
   turn=_writer_turn(db);ticket=turn.enter(time.monotonic()+5)
   with concurrent.futures.ThreadPoolExecutor(max_workers=1)as pool:
    future=pool.submit(titles.synchronize,queued,uid,now=fixed)
    try:
     time.sleep(.05);assert not future.done(),'Cold writer bypassed owned FIFO admission'
    finally:turn.leave(ticket)
    assert future.result(timeout=5)==expected
  checks.append('cold writer honors an already admitted same-file turn')
 finally:await c.asyncTearDown()
 out=dict(passed=True,proposal_only=True,checks=checks,owned_runtime_removed=not c.root.exists(),connections=len(c.server.connections))
 (h.H/'cold-writer-results-tests.json').write_text(json.dumps(out,indent=2),'utf8');print(json.dumps(out))
asyncio.run(main())
