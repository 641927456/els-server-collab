"""Real SQLite batch atomicity, per-death rollback, context and shutdown drain."""
import bootstrap
import contextlib,contextvars,json,sqlite3,tempfile,threading,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from els_server.storage.death_writer import DeathWriter
from els_server.storage.read_scope import ReadConnections
identity=contextvars.ContextVar('owned-death-identity')
def until(check):
 deadline=time.monotonic()+3
 while not check():assert time.monotonic()<deadline;time.sleep(.001)

def main():
 with tempfile.TemporaryDirectory(prefix='owned-death-batch-',dir=bootstrap.HERE)as directory:
  path=Path(directory)/'game.sqlite3'
  with contextlib.closing(sqlite3.connect(path))as db,db:
   db.execute('CREATE TABLE committed(owner INTEGER PRIMARY KEY,value INTEGER NOT NULL)')
   db.execute('CREATE TABLE linked(owner INTEGER REFERENCES committed(owner) DEFERRABLE INITIALLY DEFERRED)')
  readers=ReadConnections();writer=DeathWriter(path,readers)
  def submit(index,fail=False,foreign=False,gate=None):
   token=identity.set(index)
   def prepare(db):
    assert identity.get()==index and threading.get_ident()==writer.thread.ident
    assert db.in_transaction and db.execute('PRAGMA foreign_keys').fetchone()==(1,)
    if gate is not None:gate[0].set();assert gate[1].wait(3)
    db.execute('INSERT INTO committed VALUES(?,?)',(index,10))
    if fail:raise ValueError('Owned independent preencoding failure')
    if foreign:db.execute('INSERT INTO linked VALUES(99999)')
    return index
   try:return writer.submit(path,prepare)
   finally:identity.reset(token)
  with ThreadPoolExecutor(max_workers=9)as pool:
   with contextlib.closing(sqlite3.connect(path))as blocker:
    blocker.execute('BEGIN IMMEDIATE')
    jobs=[pool.submit(submit,i,i==2)for i in range(8)];until(lambda:writer.queue.qsize()==7)
    assert not any(f.done()for f in jobs);blocker.rollback()
   for i,future in enumerate(jobs):
    if i==2:
     try:future.result(3)
     except ValueError as e:assert str(e)=='Owned independent preencoding failure'
     else:raise AssertionError('Failed preparation committed')
    else:assert future.result(3)==i
   with contextlib.closing(sqlite3.connect(path))as db:before=db.execute('SELECT * FROM committed ORDER BY owner').fetchall()
   assert len(before)==7 and all(r[0]!=2 for r in before)and writer.maximum_batch==8
   with contextlib.closing(sqlite3.connect(path))as blocker:
    blocker.execute('BEGIN IMMEDIATE');jobs=[pool.submit(submit,20),pool.submit(submit,21,False,True)]
    until(lambda:writer.queue.qsize()==1);blocker.rollback()
   for future in jobs:
    try:future.result(3)
    except sqlite3.IntegrityError:pass
    else:raise AssertionError('Reply published before failed durable commit')
   with contextlib.closing(sqlite3.connect(path))as db:assert db.execute('SELECT * FROM committed ORDER BY owner').fetchall()==before
   gate=(threading.Event(),threading.Event());job=pool.submit(submit,30,False,False,gate);assert gate[0].wait(3)
   second=pool.submit(submit,31);until(lambda:writer.queue.qsize()==1)
   closing=pool.submit(writer.close);until(lambda:writer.closed);gate[1].set()
   assert job.result(3)==30 and second.result(3)==31;closing.result(3)
  assert not writer.thread.is_alive();writer.close();readers.close()
  with contextlib.closing(sqlite3.connect(path))as db:assert db.execute('SELECT SUM(value)FROM committed').fetchone()==(90,)
  out=dict(passed=True,ready_eight_deaths_share_commit=True,independent_preencoding_error_rolls_back_only_its_savepoint=True,deferred_commit_failure_returns_no_success_and_rolls_back_all=True,per_request_context_preserved=True,all_callers_wait_for_durable_commit=True,shutdown_drains_earlier_deaths=True)
 (bootstrap.HERE/'death-ready-writer-tests.json').write_text(json.dumps(out,indent=2),'utf8');print(json.dumps(out))
if __name__=='__main__':main()
