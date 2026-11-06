"""Native peers: XYZ delivery before blocked SQL; barriers retain durable scenes."""
import runtime_fixture as h
import asyncio,json,sqlite3,struct,threading
from contextlib import closing
from unittest.mock import patch
from profile_town import seed
from els_server.storage import position_writer as storage

def movement(x,board=0,progress=0):
    return struct.pack('>fffIBBHBii?i',float(x),0.,0.,0,0,board,progress,0,0,0,False,0)
async def main():
    c=h.f.FriendsTests();await c.asyncSetUp();out={}
    entered=threading.Event();release=threading.Event();original=storage.save_row
    try:
        uids=[seed(c,v,'OwnPos'+str(i),False)for i,v in enumerate((c.alice,c.bob))]
        a,b=[await c.peer(v)for v in(c.alice,c.bob)]
        for peer,uid in zip((a,b),uids):await peer.roster();await peer.enter_town(uid)
        await c.server.periodics.close()
        def blocked(db,uid,values):
            if uid==uids[0]:entered.set();assert release.wait(5)
            return original(db,uid,values)
        def cold():
            with closing(sqlite3.connect(c.config.state_file))as db:
                return db.execute('SELECT town,board,progress,x,y,z FROM location WHERE uid=?',(uids[0],)).fetchone()
        async def reached():
            async with asyncio.timeout(3):
                while not entered.is_set():await asyncio.sleep(.001)
        async def received(x):
            async with asyncio.timeout(3):
                while True:
                    event=await b.until(0x22e)
                    if struct.unpack_from('>Qfff',event.payload)==(uids[0],float(x),0.,0.):return
        with patch.object(storage,'save_row',blocked):
            await a.send(0x22b,movement(31));await reached()
            await received(31);assert cold()[3]!=31
            await a.send(0x22b,movement(32));await received(32)
            assert not release.is_set()and c.app.playing[c.alice['id']].account.get_location()['xyz']==(32.,0.,0.)
            await a.send(0x2ea,struct.pack('>iiB',0,0,0))
            query=asyncio.create_task(a.until(0x2eb));await asyncio.sleep(.03)
            assert not query.done(),'Business read crossed an uncommitted coordinate barrier'
            release.set();await query;assert cold()[3:]==(32.,0.,0.)
        entered.clear();release.clear()
        with patch.object(storage,'save_row',blocked):
            await a.send(0x22b,movement(43,1,2));await reached()
            notice=asyncio.create_task(received(43));await asyncio.sleep(.03)
            assert not notice.done(),'Board/progress broadcast before durable save'
            release.set();await notice;assert cold()[1:]==(1,2,43.,0.,0.)
        # A normal peer close must drain its latest accepted coordinate.
        await a.send(0x22b,movement(55,1,2));await received(55);await a.close()
        async with asyncio.timeout(4):
            while c.alice['id']in c.app.playing:await asyncio.sleep(.005)
        assert cold()[1:]==(1,2,55.,0.,0.)
        assert c.app.position_writer.snapshot()['town']['retained_actors']==0
        out.update(passed=True,native_XYZ_visible_while_SQL_blocked=True,
            later_native_move_not_blocked_by_prior_commit=True,
            native_business_query_waits_for_latest_coordinate=True,
            board_and_progress_still_durable_before_broadcast=True,
            native_disconnect_saves_latest=True,retired_actor_buffer_removed=True)
    finally:
        release.set();await c.asyncTearDown()
        out.update(owned_runtime_removed=not c.root.exists(),connections=len(c.server.connections),
            errors=[r['event']for r in c.events if r['event']in('worker_error','notification_error','connection_task_error')])
        (h.H/'town-position-native-tests.json').write_text(json.dumps(out,indent=2),'utf8')
    print(json.dumps(out));assert not out['errors']
asyncio.run(main())
