import runtime_fixture as h
import asyncio,json,sqlite3,threading
from contextlib import closing
from unittest.mock import patch
from profile_town import seed
from els_server.domain import guild_expedition as expedition,guild_services as services
P=h.H/'experiments/passive-title-guild-v2'
old_exp=h.load('own_prior_guild_expedition',P/'before-guild_expedition.py')
old_services=h.load('own_prior_guild_services',P/'before-guild_services.py')
FIELDS=('_guild_expedition_clock','_guild_expedition_projection','_guild_service_sent','_guild_contract_sent','_guild_profile_progress')

async def main():
    c=h.f.FriendsTests();await c.asyncSetUp();writer=None
    try:
        uid=seed(c,c.alice,'OwnGuildRO',False);p=await c.peer(c.alice);await p.roster();await p.enter_town(uid)
        await c.server.periodics.close();s=c.app.playing[c.alice['id']]
        def reset():
            for name in FIELDS:setattr(s,name,None)
        def projection():return{n:getattr(s,n,None)for n in FIELDS}
        def contents():
            with closing(sqlite3.connect(c.config.state_file))as db:return tuple(db.iterdump())
        before=contents()
        def compare():
            reset();a=old_services.synchronize(s);a+=old_exp.periodic(s);pa=projection()
            reset();b=services.synchronize(s);b+=expedition.periodic(s);pb=projection()
            assert a==b and pa==pb
            return dict(exact_original_events_and_projection=True)
        result=await c.app.call(compare);assert contents()==before
        writer=sqlite3.connect(c.config.state_file,timeout=10);writer.execute('BEGIN IMMEDIATE')
        await c.app.call(reset)
        def read_current():
            out=services.synchronize(s)+expedition.periodic(s)
            return out,projection()
        current,current_projection=await c.app.call(read_current)
        assert writer.in_transaction and current==[]
        await c.app.call(reset);started=threading.Event();connect=sqlite3.connect
        def traced(*args,**kwargs):
            db=connect(*args,**kwargs)
            def trace(sql):
                if sql.lstrip().upper().startswith('BEGIN IMMEDIATE'):started.set()
            db.set_trace_callback(trace);return db
        with patch.object(sqlite3,'connect',traced):
            prior=asyncio.create_task(c.app.call(lambda:old_services.synchronize(s)+old_exp.periodic(s)))
            try:
                async with asyncio.timeout(3):
                    while not started.is_set():await asyncio.sleep(.001)
                assert not prior.done()and writer.in_transaction
            finally:writer.commit()
            assert await prior==current and projection()==current_projection
        writer.close();writer=None;assert contents()==before
        out=dict(passed=True,actual_native_town_role=True,exact_original_events_and_projection=True,complete_SQL_unchanged=True,real_other_SQLite_writer_held=True,new_empty_expedition_and_service_reads_finish_with_writer_held=True,prior_empty_expedition_waited_for_writer=True,existing_clock_and_projection_semantics_preserved=True)
    finally:
        if writer is not None:writer.rollback();writer.close()
        await c.asyncTearDown()
    out.update(owned_runtime_removed=not c.root.exists(),connections=len(c.server.connections))
    (h.H/'passive-guild-negative-tests.json').write_text(json.dumps(out,indent=2),'utf8');print(json.dumps(out))
asyncio.run(main())
