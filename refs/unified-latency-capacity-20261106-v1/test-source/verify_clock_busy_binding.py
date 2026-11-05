"""Busy deferral preserves distinct save binding errors and actor-free reports."""
import bootstrap,json,sqlite3,tempfile,threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from els_server.storage import clock_writer as module
with tempfile.TemporaryDirectory(prefix='owned-clock-busy-binding-',dir=bootstrap.HERE)as raw:
 root=Path(raw);path=root/'save.sqlite3';other=root/'other.sqlite3'
 with closing(sqlite3.connect(path))as db,db:db.execute('CREATE TABLE entries(id INTEGER PRIMARY KEY)')
 writer=module.ClockWriter(path);entered=threading.Event();release=threading.Event();commit=module.commit_write;callbacks=[]
 def delayed(db):entered.set();assert release.wait(5);return commit(db)
 def write(db):callbacks.append(True);db.execute('INSERT INTO entries VALUES(1)')
 try:
  with ThreadPoolExecutor(max_workers=1)as pool,patch.object(module,'commit_write',delayed):
   first=pool.submit(writer.commit,((path,write),),stop=True);assert entered.wait(3)
   errors,physical=writer.commit(((path,write),(other,write)),stop=False)
   assert physical is None and len(errors)==2 and errors[0].sqlite_errorcode==sqlite3.SQLITE_BUSY and type(errors[1])is ValueError
   assert all(error.__traceback__ is None for error in errors)and callbacks==[True]and not other.exists()
   release.set();assert first.result(timeout=3)==((None,),None)
 finally:release.set();writer.close()
 assert writer.jobs==0
 try:writer.commit(((path,write),),stop=False)
 except RuntimeError as error:assert str(error)=='Clock writer closed'
 else:raise AssertionError('Closed writer accepted a busy observation')
out=dict(passed=True,actual_combined_v2=True,wrong_save_never_opened=True,correct_save_BUSY_distinct_from_wrong_save_error=True,no_extra_callback=True,no_traceback_retention=True,closed_writer_refuses=True,owned_runtime_removed=not root.exists())
(bootstrap.HERE/'clock-busy-binding-tests.json').write_text(json.dumps(out,indent=2),'utf8');print(json.dumps(out))
