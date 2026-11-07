"""A delayed original inventory reader must not hold up other town actors."""
import runtime_fixture as h
import asyncio,json,sqlite3,struct,sys,threading
from contextlib import closing
from dataclasses import replace
from unittest.mock import patch
from profile_town import seed
from els_server.domain.local_session import LocalAccount
from els_server.protocol.protocol_codec import Event
expected_free='--expected-free'in sys.argv
gate=h.load('own_transition_gate',h.ROOT/'analysis/glass-door-20261104-v1/repair-v3/gate_probe.py')

async def main():
    original=h.f.ServerConfig;h.f.ServerConfig=lambda **kw:replace(original(**kw),max_connections=16)
    c=h.f.FriendsTests();await c.asyncSetUp();entered=threading.Event();release=threading.Event()
    try:
        identities=[c.alice,c.bob,c.app.registry.create('owntransition')]
        uids=[seed(c,v,'OwnTrans'+str(i),False)for i,v in enumerate(identities)]
        peers=[await c.peer(v)for v in identities]
        for p,uid in zip(peers,uids):await p.roster();await p.enter_town(uid)
        await c.server.periodics.close();moving,observer,dungeon=peers;uid=uids[2]
        session=c.app.playing[identities[2]['id']];ordinary=getattr(c.app.dungeon_workers,'solo_transition',lambda *args:False)
        assert ordinary(session.handle,(Event(0x202,kind=0x7d4,payload=struct.pack('>ii',1,34710)),))==expected_free
        from els_server.domain import normal_fatigue_flow
        original_read=normal_fatigue_flow.admission_result
        def slow_read(actor,identity):
            if actor is session:entered.set();assert release.wait(5)
            return original_read(actor,identity)
        async def delivered():
            while True:
                e=await observer.until(0x22e)
                if struct.unpack_from('>Qfff',e.payload)==(uids[0],321.,0.,0.):return
        with patch.object(normal_fatigue_flow,'admission_result',slow_read):
            await dungeon.send(0x7d4,struct.pack('>ii',1,34710))
            async with asyncio.timeout(3):
                while not entered.is_set():await asyncio.sleep(.001)
            payload=struct.pack('>fffIBBHBii?i',321.,0.,0.,0,0,0,0,0,0,0,False,0)
            await moving.send(0x22b,payload);notice=asyncio.create_task(delivered())
            await asyncio.sleep(.1);town_free=notice.done();assert town_free==expected_free,(town_free,expected_free)
            release.set();assert(await dungeon.until(0x7d5)).payload[:4]==bytes(4)
            if not notice.done():
                # Idle notifications are deliberately closed in this fixture.
                # Native reads drain the baseline's already queued movement.
                await moving.send(0x48d);await moving.until(0x48f)
                await observer.send(0x48d)
            await notice
        await dungeon.send(0x382,gate.ENTRY);assert(await dungeon.until(0x383)).payload[:4]==bytes(4);await dungeon.until(0x14a)
        await dungeon.send(0x91,struct.pack('>ii',100,0));await dungeon.until(0xb2)
        await dungeon.send(0xb3,bytes(9));await dungeon.until(0xbd)
        body=bytes.fromhex(json.loads((h.ROOT/'analysis/client-6c6b5180/end-request-native.json').read_bytes())['payload_hex'])
        await dungeon.send(0x67,body);assert(await dungeon.until(0x68)).payload==bytes(31)
        await dungeon.send(0x225,struct.pack('>iB',20000,0));assert(await dungeon.until(0x226)).payload[:4]==bytes(4)
        await dungeon.send(0x227,struct.pack('>fffBH',1.,2.,3.,0,0));assert(await dungeon.until(0x228)).payload==bytes(4)
        assert session.phase=='town_ready'and c.app.world.members[session]==(1,20000)
        with closing(sqlite3.connect(c.config.state_file))as db:assert all(ed==0 for(ed,)in db.execute('SELECT ed FROM reward_balances'))
        out=dict(passed=True,proposal=expected_free,native_three_role_fixture=True,original_fatigue_preflight_delayed=True,other_town_native_move_delivered_before_reader_release=town_free,normal_admission_load_end_town_return=True,no_forced_room_or_server_phase=True,economic_delta=0)
    finally:release.set();await c.asyncTearDown()
    out.update(owned_runtime_removed=not c.root.exists(),connections=len(c.server.connections))
    name='solo-selection-scope-proposal-tests.json'if expected_free else'solo-selection-scope-v10-control-tests.json'
    (h.H/name).write_text(json.dumps(out,indent=2),'utf8');print(json.dumps(out))
asyncio.run(main())
