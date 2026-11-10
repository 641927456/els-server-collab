"""Controlled pending-writer regression for the original shared item loader."""
from qa_environment import F
from pathlib import Path
from contextlib import closing
import hashlib,json,sqlite3,sys,tempfile,threading,time,traceback
from els_server.storage.game_schema import prepare
from els_server.storage.characters import Characters
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage.read_scope import committed_reads,snapshot_connection
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS


def run():
    baseline='--baseline'in sys.argv;report=dict(ok=False,baseline_reproducer=baseline,production_database_access=False)
    with tempfile.TemporaryDirectory(prefix='owned-reader-contention-',dir=F)as folder:
        path=Path(folder)/'game.sqlite3';prepare(path)
        owner=Characters(path,1).create('OwnReader',1,'owned-reader-create')['uid']
        with closing(sqlite3.connect(path))as db,db:
            assert db.execute('PRAGMA journal_mode').fetchone()[0]=='delete'
            grant_items(db,[dict(template=710001,metadata=VERIFIED_TEMPLATES[710001],group=TEMPLATE_BAG_GROUPS[710001],quantity=1)],owner)
            db.execute('CREATE TABLE own_contention(id INTEGER PRIMARY KEY,value INTEGER)');db.execute('INSERT INTO own_contention VALUES(1,0)')
            expected=load_items(db,owner)
        attempted=threading.Event();out={};worker=None
        def writer():
            try:
                with closing(sqlite3.connect(path,timeout=.6))as db,db:
                    db.execute('BEGIN IMMEDIATE');db.execute('UPDATE own_contention SET value=1')
                    attempted.set();db.commit();out['committed']=True
            except BaseException as error:out.update(committed=False,code=getattr(error,'sqlite_errorcode',None),error=repr(error))
        try:
            with committed_reads():
                with snapshot_connection(path)as outer:
                    outer.execute('BEGIN');outer.execute('SELECT value FROM own_contention').fetchall()
                    with snapshot_connection(path)as nested:
                        assert nested is not outer
                        nested.execute('BEGIN');assert load_items(nested,owner)==expected
                report['independent_nested_reader_passed']=True
                with snapshot_connection(path)as db:
                    db.execute('BEGIN');db.execute('SELECT value FROM own_contention').fetchall()
                    worker=threading.Thread(target=writer);worker.start();assert attempted.wait(2)
                    #A fresh reader cannot enter while the writer is PENDING.
                    pending=False;deadline=time.monotonic()+.3
                    while time.monotonic()<deadline:
                        try:
                            with closing(sqlite3.connect(path,timeout=0))as probe:probe.execute('SELECT value FROM own_contention').fetchall()
                        except sqlite3.OperationalError as error:
                            assert error.sqlite_errorcode==sqlite3.SQLITE_BUSY;pending=True;break
                        time.sleep(.002)
                    assert pending,'Controlled writer did not reach its pending commit'
                    start=time.perf_counter();items=load_items(db,owner);report['loader_seconds']=time.perf_counter()-start
                    assert items==expected
            worker.join(2);assert not worker.is_alive();report['writer']=out
            with closing(sqlite3.connect(path))as db:report['committed_value']=db.execute('SELECT value FROM own_contention').fetchall()[0][0]
            if baseline:
                assert out.get('committed')is False and out.get('code')==sqlite3.SQLITE_BUSY
                assert report['loader_seconds']>=.45 and report['committed_value']==0
            else:
                assert out.get('committed')is True and report['committed_value']==1
                assert report['loader_seconds']<.3
            report['ok']=True
        except BaseException:report['error']=traceback.format_exc()
        finally:
            if worker is not None:worker.join(2)
            report['writer']=out
    report['source_sha256']={p.relative_to(F/'source-v1').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in(F/'source-v1').rglob('*.py')}
    (F/('reader-contention-'+str(time.time_ns())+'.json')).write_bytes((json.dumps(report,indent=2)+'\n').encode())
    print(json.dumps(report));return report['ok']


if __name__=='__main__':raise SystemExit(not run())
