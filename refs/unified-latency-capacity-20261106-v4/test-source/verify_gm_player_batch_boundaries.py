import runtime_fixture as h
import asyncio,json,sqlite3
from contextlib import closing
from unittest.mock import patch
from profile_town import seed
from els_server.gm_runtime import Runtime
proposal=h.load('owned_gm_batch_boundaries',h.H/'experiments/gm-player-batch-v2/gm_runtime.py')

async def main():
    c=h.f.FriendsTests();await c.asyncSetUp()
    try:
        identities=[c.alice,c.bob];uids=[seed(c,v,'OwnGMEdge'+str(i),False)for i,v in enumerate(identities)]
        peers=[await c.peer(v)for v in identities]
        for p,uid in zip(peers,uids):await p.roster();await p.enter_town(uid)
        await c.server.periodics.close()
        old=Runtime(c.app,c.server,c.root/'gm-old.jsonl');new=proposal.Runtime(c.app,c.server,c.root/'gm-new.jsonl')
        accounts=[c.app.playing[v['id']].account for v in identities]
        def same():
            a=old.players();b=new.players();assert a==b;return b
        def snapshot():
            with closing(sqlite3.connect(c.config.state_file))as db:return tuple(db.iterdump())
        before=snapshot()
        def cold():
            saved=accounts[0].reward_store
            try:
                accounts[0].reward_store=None;a=old.players();assert accounts[0].reward_store is not None
                accounts[0].reward_store=None;b=new.players();assert accounts[0].reward_store is not None
                assert a==b
            finally:accounts[0].reward_store=saved
        await c.app.call(cold)
        store=accounts[0].reward_store
        with patch.object(store,'balances',lambda:dict(ed=123,experience=0,revision=0)):
            rows=await c.app.call(same);assert next(r for r in rows if r['uid']==uids[0])['ed']==123
        with patch.object(accounts[0],'enable_rewards',lambda:store):await c.app.call(same)
        assert snapshot()==before
        with closing(sqlite3.connect(c.config.state_file))as db,db:
            balance=db.execute('SELECT * FROM reward_balances WHERE uid=?',(uids[0],)).fetchone()
            db.execute('DELETE FROM reward_balances WHERE uid=?',(uids[0],))
        def rejected():
            errors=[]
            for runtime in(old,new):
                try:runtime.players()
                except ValueError as error:errors.append(str(error))
            assert errors==['Invalid persisted reward balances']*2
        try:await c.app.call(rejected)
        finally:
            with closing(sqlite3.connect(c.config.state_file))as db,db:db.execute('INSERT INTO reward_balances VALUES(?,?,?,?)',balance)
        with closing(sqlite3.connect(c.config.state_file))as db,db:db.execute("UPDATE reward_balances SET ed='invalid'WHERE uid=?",(uids[0],))
        try:await c.app.call(rejected)
        finally:
            with closing(sqlite3.connect(c.config.state_file))as db,db:db.execute('UPDATE reward_balances SET ed=?WHERE uid=?',(balance[1],uids[0]))
        with closing(sqlite3.connect(c.config.state_file))as db,db:
            db.execute('ALTER TABLE reward_balances RENAME TO reward_balances_private_original')
            db.execute('CREATE VIEW reward_balances AS SELECT * FROM reward_balances_private_original')
        try:await c.app.call(same)
        finally:
            with closing(sqlite3.connect(c.config.state_file))as db,db:
                db.execute('DROP VIEW reward_balances');db.execute('ALTER TABLE reward_balances_private_original RENAME TO reward_balances')
        out=dict(passed=True,actual_native_selected_roles=2,cold_reward_store_original_initialization=True,overridden_balance_and_initializer_original=True,missing_and_invalid_balance_original_errors=True,nonstandard_reward_schema_original_reader=True,no_SQL_write_by_status_reader=True,proposal_only=True)
    finally:await c.asyncTearDown()
    out.update(owned_runtime_removed=not c.root.exists(),connections=len(c.server.connections))
    (h.H/'gm-player-batch-boundary-tests.json').write_text(json.dumps(out,indent=2),'utf8');print(json.dumps(out))
asyncio.run(main())
