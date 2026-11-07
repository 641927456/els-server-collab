"""Reuse exact original ledger oracle and add a real queued-stall case."""
import runtime_fixture as h
from concurrent.futures import ThreadPoolExecutor
import threading
source=(h.H/'verify_clock_pair.py').read_text('utf8')
anchor='  out.update(passed=True,two_original_commits_become_one=True'
assert source.count(anchor)==1
case='''  path,now,a,t,observe=create('queued-real-clock-stall');writer=writers[-1];wall=now[1];before=contents(path)
  entered=threading.Event();release=threading.Event();physical=batch_module.commit_write
  def delayed(db):entered.set();assert release.wait(5);return physical(db)
  def dummy(db):db.execute('SELECT 1').fetchone()
  with ThreadPoolExecutor(max_workers=1)as pool,patch.object(batch_module,'commit_write',delayed):
   blocking=pool.submit(writer.commit,((path,dummy),),stop=True);assert entered.wait(3)
   try:
    now[:]=[12.,wall+2];started=time.perf_counter();observe();nonblocking_ms=(time.perf_counter()-started)*1000
    assert not blocking.done()and a.committed==0 and t.cursor==wall
    assert a._deferred==a._attempt and t._deferred==t._attempt and contents(path)==before
   finally:release.set()
   assert blocking.result(timeout=3)==((None,),None)
  now[:]=[13.,wall+3];observe();assert a.committed==3 and t.cursor==wall+3
  now[:]=[14.,wall+4];observe(stop=True);assert a.closed and t.closed
  out.update(queued_stall_returns_before_physical_release=True,nonblocking_ms=nonblocking_ms,both_cursors_restored_on_queue_BUSY=True,whole_deferred_union_commits_next_observation=True,normal_stop_flushes_remaining_interval=True)
'''
source=source.replace(anchor,case+anchor).replace("h.H/'clock-pair-tests.json'","h.H/'clock-nonblocking-pair-tests.json'")
exec(compile(source,str(h.H/'verify_clock_pair.py')+'-nonblocking','exec'),globals())
