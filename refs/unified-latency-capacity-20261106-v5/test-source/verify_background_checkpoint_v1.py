import bootstrap
from pathlib import Path
from contextlib import closing
import json,sqlite3,tempfile,time
from unittest.mock import patch
from els_server.storage.wal_checkpoints import WALCheckpoints
H=bootstrap.HERE
import ctypes,psutil
native=ctypes.WinDLL('kernel32',use_last_error=True)
native.GetCurrentThread.restype=ctypes.c_void_p
native.GetThreadPriority.argtypes=[ctypes.c_void_p];native.GetThreadPriority.restype=ctypes.c_int
parent_before=(native.GetThreadPriority(native.GetCurrentThread()),int(psutil.Process().nice()),int(psutil.Process().ionice()))
def wait_for(check):
    until=time.monotonic()+3
    while not check():
        if time.monotonic()>=until:raise TimeoutError('Owned passive checkpoint did not complete its next scheduled pass')
        time.sleep(.01)
with tempfile.TemporaryDirectory(prefix='owned-passive-checkpoint-',dir=H)as raw:
    path=Path(raw)/'game.sqlite3';worker=None
    try:
        with closing(sqlite3.connect(path))as db,closing(sqlite3.connect(path))as reader:
            assert db.execute('PRAGMA journal_mode=WAL').fetchone()==('wal',)
            db.execute('CREATE TABLE owned(value INTEGER)');db.execute('INSERT INTO owned VALUES(1)');db.commit()
            before=(db.execute('PRAGMA synchronous').fetchone(),db.execute('PRAGMA wal_autocheckpoint').fetchone())
            worker=WALCheckpoints(path);worker.prepare();first=worker.snapshot()
            assert first['background_thread_priority']is not None and first['background_thread_priority']<0
            assert first['prewarmed']and first['last'][0]==0 and first['last'][1]==first['last'][2]
            reader.execute('BEGIN');assert reader.execute('SELECT value FROM owned').fetchone()==(1,)
            db.execute('UPDATE owned SET value=2');db.commit()
            runs=worker.snapshot()['runs'];wait_for(lambda:worker.snapshot()['runs']>runs)
            held=worker.snapshot();assert held['last'][1]>held['last'][2]and reader.execute('SELECT value FROM owned').fetchone()==(1,)
            reader.rollback();runs=held['runs'];wait_for(lambda:worker.snapshot()['runs']>runs)
            released=worker.snapshot();assert released['last'][0]==0 and released['last'][1]==released['last'][2]
            assert before==(db.execute('PRAGMA synchronous').fetchone(),db.execute('PRAGMA wal_autocheckpoint').fetchone())==((2,),(1000,))
            assert db.execute('PRAGMA journal_mode').fetchone()==('wal',)
    finally:
        if worker is not None:worker.close()
    assert not worker.thread.is_alive()
    with closing(sqlite3.connect(path))as cold:assert cold.execute('SELECT value FROM owned').fetchone()==(2,)
    missing=WALCheckpoints(Path(raw)/'missing.sqlite3')
    try:missing.prepare()
    except sqlite3.OperationalError:pass
    else:raise AssertionError('Missing save path silently succeeded')
    assert not missing.thread.is_alive()and not missing.path.exists()
    original_connect=sqlite3.connect
    class FailingConnection(sqlite3.Connection):
        checkpoints=0
        def execute(self,sql,*args,**kwargs):
            if sql=='PRAGMA main.wal_checkpoint(PASSIVE)':
                self.checkpoints+=1
                if self.checkpoints==2:raise sqlite3.OperationalError('owned checkpoint I/O failure')
            return super().execute(sql,*args,**kwargs)
    with patch.object(sqlite3,'connect',side_effect=lambda *args,**kwargs:original_connect(*args,**kwargs,factory=FailingConnection)):
        failed=WALCheckpoints(path);failed.prepare();wait_for(failed.finished.done)
        for observe in(failed.check,failed.close):
            try:observe()
            except sqlite3.OperationalError as error:assert str(error)=='owned checkpoint I/O failure'
            else:raise AssertionError('Background checkpoint failure silently succeeded')
        assert not failed.thread.is_alive()
    with closing(sqlite3.connect(path))as cold:assert cold.execute('SELECT value FROM owned').fetchone()==(2,)
assert parent_before==(native.GetThreadPriority(native.GetCurrentThread()),int(psutil.Process().nice()),int(psutil.Process().ionice()))
out=dict(passed=True,background_worker_priority=first['background_thread_priority'],calling_thread_and_process_priority_unchanged=True,startup_checkpoint_prepared=True,actual_read_snapshot_held=True,PASSIVE_did_not_wait_for_reader_or_writer=True,reader_snapshot_and_foreground_commit_correct=True,next_scheduled_pass_drains_after_reader_release=True,FULL_WAL_and_original_1000_page_threshold_unchanged=True,cold_SQL_exact=True,normal_stop_thread_joined=True,missing_save_error_explicit_and_no_creation=True,background_IO_error_explicit_and_thread_joined=True,owned_runtime_removed=not Path(raw).exists())
(H/'background-checkpoint-v1-tests.json').write_text(json.dumps(out,indent=2),'utf8');print(json.dumps(out))
