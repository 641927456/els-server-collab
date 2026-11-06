import runtime_fixture as h
import asyncio,concurrent.futures,json,sqlite3,threading
from contextlib import closing
from unittest.mock import patch
from profile_town import seed
from els_server.storage import titles as current
from els_server.domain import titles as rules
old=h.load('own_original_title_state',h.H/'experiments/passive-title-guild-v2/before-titles.py')
NOW=1800000000

async def main():
    c=h.f.FriendsTests();await c.asyncSetUp();writer=None
    try:
        uid=seed(c,c.alice,'OwnTitleRO',False);paths=[c.root/'title-before.sqlite3',c.root/'title-proposal.sqlite3']
        for path in paths:
            with closing(sqlite3.connect(c.config.state_file))as source,closing(sqlite3.connect(path))as target:source.backup(target)
            with closing(sqlite3.connect(path))as db:assert db.execute('PRAGMA journal_mode=WAL').fetchone()==('wal',);assert db.execute('PRAGMA synchronous').fetchone()==(2,)
        def contents(path):
            with closing(sqlite3.connect(path))as db:return tuple(db.iterdump())
        def sql_both(statement,args=()):
            for path in paths:
                with closing(sqlite3.connect(path))as db,db:db.execute(statement,args)
        cases=[];connect=sqlite3.connect;queries=[]
        def traced(*args,**kwargs):
            db=connect(*args,**kwargs);db.set_trace_callback(queries.append);return db
        def compare(name):
            queries.clear()
            with patch.object(sqlite3,'connect',traced):a=old.state(paths[0],uid)
            before_writes=sum(s.lstrip().upper().startswith('UPDATE TITLE_EQUIPMENT')for s in queries);queries.clear()
            with patch.object(sqlite3,'connect',traced):b=current.state(paths[1],uid)
            after_writes=sum(s.lstrip().upper().startswith('UPDATE TITLE_EQUIPMENT')for s in queries)
            assert a==b and contents(paths[0])==contents(paths[1]),name
            cases.append(dict(name=name,exact_original_state_and_complete_SQL=True,title_UPDATEs=[before_writes,after_writes]))
            return b
        with patch('time.time',return_value=NOW):
            compare('optional_equipment_absent')
            for path in paths:
                with closing(sqlite3.connect(path))as db,db:current.schema(db)
            sql_both('INSERT INTO title_equipment VALUES(?,0)',(uid,))
            assert compare('zero_equipment')['title']==0 and cases[-1]['title_UPDATEs']==[1,0]
            with closing(sqlite3.connect(paths[0]))as db:character=old.character(db,uid)
            title=min(int(key)for key in rules.catalog()['titles']if rules.eligible(character,int(key)))
            scope,subject=rules.scope(character,title)
            sql_both('INSERT INTO title_ownership VALUES(?,?,?,?,?,?)',(scope,subject,title,'owned-title-state',NOW-100,0))
            sql_both('UPDATE title_equipment SET title=?WHERE owner=?',(title,uid))
            assert compare('active_owned_title')['title']==title
            sql_both('UPDATE title_ownership SET expires_at=?',(NOW,))
            assert compare('expired_equipment_cleanup')['title']==0
            assert cases[-1]['title_UPDATEs']==[1,1]
            for path,module in zip(paths,(old,current)):
                try:module.state(path,999999)
                except ValueError as error:assert str(error)=='Unknown title owner'
                else:raise AssertionError('Unknown title owner accepted')
            # The old zero-row UPDATE waits for a genuine other SQLite writer.
            path=paths[1];writer=sqlite3.connect(path,timeout=10);writer.execute('BEGIN IMMEDIATE')
            update_entered=threading.Event()
            def observed(*args,**kwargs):
                db=connect(*args,**kwargs)
                def trace(statement):
                    if statement.lstrip().upper().startswith('UPDATE TITLE_EQUIPMENT'):update_entered.set()
                db.set_trace_callback(trace);return db
            with concurrent.futures.ThreadPoolExecutor(max_workers=1)as pool,patch.object(sqlite3,'connect',observed):
                before=pool.submit(old.state,path,uid)
                try:
                    async with asyncio.timeout(3):
                        while not update_entered.is_set():await asyncio.sleep(.001)
                    assert not before.done()
                    value=current.state(path,uid)
                    assert writer.in_transaction and not before.done()and value['title']==0
                finally:writer.commit()
                assert before.result(timeout=3)==value
            writer.close();writer=None
        out=dict(passed=True,cases=cases,unknown_owner_original_error=True,real_other_SQLite_writer_held=True,readonly_result_completed_while_writer_held=True,original_noop_UPDATE_waited_for_writer=True,stale_title_cleanup_still_durable=True)
    finally:
        if writer is not None:writer.rollback();writer.close()
        await c.asyncTearDown()
    out.update(owned_runtime_removed=not c.root.exists(),connections=len(c.server.connections))
    (h.H/'passive-title-read-v2-tests.json').write_text(json.dumps(out,indent=2),'utf8');print(json.dumps(out))
asyncio.run(main())
