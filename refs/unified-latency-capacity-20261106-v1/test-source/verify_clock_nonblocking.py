"""A stalled real SQL commit cannot queue a best-effort clock behind it."""
import bootstrap
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
import json,sqlite3,tempfile,threading,time
from els_server.storage import clock_writer as module
with tempfile.TemporaryDirectory(prefix='owned-clock-nonblocking-',dir=bootstrap.HERE)as raw:
 path=Path(raw)/'state.sqlite3'
 with closing(sqlite3.connect(path))as db,db:db.execute('CREATE TABLE entries(id INTEGER PRIMARY KEY)')
 writer=module.ClockWriter(path);entered=threading.Event();release=threading.Event();ran=[];commit=module.commit_write
 def delayed(db):entered.set();assert release.wait(5);return commit(db)
 def write(index):
  def apply(db):ran.append(index);db.execute('INSERT INTO entries VALUES(?)',(index,))
  return apply
 try:
  writer.prepare()
  with ThreadPoolExecutor(max_workers=3)as callers,patch.object(module,'commit_write',delayed):
   first=callers.submit(writer.commit,((path,write(1)),),stop=True);assert entered.wait(3)
   started=time.perf_counter();busy=callers.submit(writer.commit,((path,write(2)),),stop=False)
   report,physical=busy.result(timeout=1);elapsed=(time.perf_counter()-started)*1000
   assert physical is None and len(report)==1 and report[0].sqlite_errorcode==sqlite3.SQLITE_BUSY and report[0].__traceback__ is None
   assert not first.done()and ran==[1]
   final=callers.submit(writer.commit,((path,write(3)),),stop=True)
   time.sleep(.05);assert not final.done(),'Final flush skipped durable writer'
   release.set();assert first.result(timeout=3)==((None,),None)and final.result(timeout=3)==((None,),None)
  assert writer.commit(((path,write(2)),),stop=False)==((None,),None)
  with closing(sqlite3.connect(path))as db:assert db.execute('SELECT id FROM entries ORDER BY id').fetchall()==[(1,),(2,),(3,)]
  assert writer.jobs==0 and writer.snapshot()['nonblocking_deferrals']==1
 finally:release.set();writer.close()
out=dict(passed=True,proposal_only=True,stalled_real_commit_kept_open=True,nonfinal_observation_returns_BUSY_before_stall_released=True,nonfinal_ms=elapsed,deferred_callback_not_executed=True,final_flush_waits_for_physical_commit=True,next_ordinary_observation_can_commit=True,report_has_no_traceback=True,owned_runtime_removed=not Path(raw).exists())
(bootstrap.HERE/'clock-nonblocking-tests.json').write_text(json.dumps(out,indent=2),'utf8');print(json.dumps(out))
