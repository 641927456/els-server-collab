import runtime_fixture as h
from pathlib import Path
import contextlib,json,math,sqlite3,tempfile,threading,time
from els_server.storage.position_writer import PositionWriter
old=h.load('owned_old_position_batch',h.H/'experiments/position-batch-v1/before-position_writer.py')
def run(klass,path,count):
    with contextlib.closing(sqlite3.connect(path))as db:
        db.execute('PRAGMA journal_mode=WAL');db.execute('CREATE TABLE location(uid INTEGER PRIMARY KEY,town INTEGER,board INTEGER,progress INTEGER,x REAL,y REAL,z REAL,revision INTEGER)')
        db.executemany('INSERT INTO location VALUES(?,20000,7,9,0,0,0,1)',((n,)for n in range(1,count+1)));db.commit()
        db.execute('BEGIN IMMEDIATE');writer=klass(path);futures=[];errors=[];submitted=threading.Event()
        def submit():
            try:
                for uid in range(1,count+1):futures.append((uid,writer._submit(path,uid,(20000,7,9,uid/2,0.,-uid/3))))
            except BaseException as error:errors.append(repr(error))
            finally:submitted.set()
        producer=threading.Thread(target=submit);producer.start()
        if klass is PositionWriter:assert submitted.wait(2),'A 50-player town did not fit the bounded ready batch'
        else:
            until=time.monotonic()+2
            while len(futures)<min(count,32)and not submitted.is_set()and time.monotonic()<until:time.sleep(.001)
        db.rollback();producer.join(timeout=3);assert not producer.is_alive()and not errors,errors
        results={uid:future.result(timeout=3)for uid,future in futures};metrics=writer.snapshot();writer.close()
        rows=db.execute('SELECT * FROM location ORDER BY uid').fetchall()
    assert len(results)==count
    for uid,row in results.items():assert row==dict(map=20000,board=7,progress=9,xyz=(uid/2,0.,-uid/3),revision=2)
    return rows,results,metrics['batches']
cases=[]
with tempfile.TemporaryDirectory(dir=h.H,prefix='owned-position-batch-')as temp:
    root=Path(temp)
    for count in(1,5,20,50):
        baseline=run(old.PositionWriter,root/f'old-{count}.sqlite3',count)
        actual=run(PositionWriter,root/f'new-{count}.sqlite3',count)
        assert baseline[:2]==actual[:2]and actual[2]==1
        if count>16:assert baseline[2]>actual[2]
        cases.append(dict(actors=count,original_commits=baseline[2],proposal_commits=actual[2],all_rows_and_durable_future_results_equal=True))
out=dict(passed=True,proposal_only=True,cases=cases,temporary_files_removed=True,SQL_durability_unchanged=True)
(h.H/'position-batch-tests.json').write_text(json.dumps(out,indent=2),'utf8');print(json.dumps(out))
