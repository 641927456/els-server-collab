"""Actual GM rows, original owner rejection, overrides and fresh SQL values."""
import runtime_fixture as h
import asyncio,json,time,statistics,sqlite3
from contextlib import closing
from dataclasses import replace
from unittest.mock import patch
from profile_town import seed
from els_server.storage.read_scope import _ReadScope
from els_server.gm_runtime import Runtime
proposal=h.load('owned_gm_identity_batch',h.H/'experiments/gm-player-batch-v2/gm_runtime.py')

async def main():
    original=h.f.ServerConfig;h.f.ServerConfig=lambda **kw:replace(original(**kw),max_connections=64)
    c=h.f.FriendsTests();await c.asyncSetUp()
    try:
        identities=[c.alice,c.bob]+[c.app.registry.create('owngmb'+str(i))for i in range(2,25)]
        uids=[seed(c,v,'OwnGMB'+str(i),False)for i,v in enumerate(identities)]
        peers=[await c.peer(v)for v in identities]
        for p,uid in zip(peers,uids):await p.roster();await p.enter_town(uid)
        await c.server.periodics.close()
        old=Runtime(c.app,c.server,c.root/'own-gm-old.jsonl');new=proposal.Runtime(c.app,c.server,c.root/'own-gm-new.jsonl')
        def sql_snapshot():
            with closing(sqlite3.connect(c.config.state_file))as db:return tuple(db.iterdump())
        before=sql_snapshot()
        def measure(runtime):
            statements=[];connections=[];open_reader=_ReadScope.open
            def trace(sql):statements.append(sql)
            def opened(scope,path):
                db=open_reader(scope,path);db.set_trace_callback(trace);connections.append(db);return db
            for observers,_,readers in c.app.read_connections.workers.values():
                for db in(*observers.values(),*readers.values()):db.set_trace_callback(trace);connections.append(db)
            try:
                with patch.object(_ReadScope,'open',opened):
                    started=time.perf_counter();rows=runtime.players();elapsed=(time.perf_counter()-started)*1000
                return rows,dict(pooled_reader_SELECTs=sum(s.lstrip().upper().startswith(('SELECT','WITH'))for s in statements),pooled_reader_statements=len(statements),worker_wall_ms=elapsed)
            finally:
                for db in connections:db.set_trace_callback(None)
        def compare():
            a,before=measure(old);b,after=measure(new)
            assert a==b
            return dict(existing=before,proposal=after,exact_GM_rows=True)
        measured=[await c.app.call(compare)for _ in range(10)]
        assert all(v['proposal']['pooled_reader_SELECTs']<v['existing']['pooled_reader_SELECTs']for v in measured)
        assert sql_snapshot()==before
        account=c.app.playing[c.alice['id']].account
        with patch.object(account,'character_identity',lambda:None):
            await c.app.call(compare)
        with patch.object(account,'get_reward_balances',lambda:dict(ed=12345)):
            await c.app.call(compare)
        with closing(sqlite3.connect(c.config.state_file))as db,db:
            db.execute('UPDATE characters SET level=98,revision=revision+1 WHERE uid=?',(uids[0],))
        with closing(sqlite3.connect(c.config.state_file))as db,db:
            db.execute('UPDATE reward_balances SET ed=54321,revision=revision+1 WHERE uid=?',(uids[0],))
        def changed():
            a=old.players();b=new.players();assert a==b
            row=next(r for r in b if r['uid']==uids[0]);assert row['level']==98 and row['ed']==54321
        await c.app.call(changed)
        with closing(sqlite3.connect(c.config.state_file))as db,db:
            db.execute('UPDATE character_owners SET account_id=account_id+100 WHERE uid=?',(uids[5],))
        def rejected():
            errors=[]
            for runtime in(old,new):
                try:runtime.players()
                except ValueError as error:errors.append(str(error))
            assert len(errors)==2 and errors[0]==errors[1]
        await c.app.call(rejected)
        with closing(sqlite3.connect(c.config.state_file))as db,db:
            db.execute('UPDATE character_owners SET account_id=account_id-100 WHERE uid=?',(uids[5],))
        out=dict(passed=True,proposal_only=True,real_native_town_actors=25,measurements=measured,worker_wall_median_ms={key:statistics.median(v[key]['worker_wall_ms']for v in measured)for key in('existing','proposal')},original_balance_reader_and_override_preserved=True,identity_override_preserved=True,fresh_other_writer_identity_change=True,foreign_owner_original_error_preserved=True,complete_SQL_unchanged_by_status_reads=True)
    finally:await c.asyncTearDown()
    out.update(owned_runtime_removed=not c.root.exists(),connections=len(c.server.connections))
    (h.H/'gm-player-batch-v2-tests.json').write_text(json.dumps(out,indent=2),'utf8');print(json.dumps(out))
asyncio.run(main())
