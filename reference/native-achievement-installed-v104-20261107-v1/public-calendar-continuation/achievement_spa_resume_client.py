"""Continue after the committed purchase whose full-row assertion crossed midnight."""
import asyncio,struct,time
from achievement_protocol_client import connect
from achievement_spa_client import heartbeat,last_state,purchase,eggs,ENTRY
from els_server.domain.quick_bindings import item_binding
from els_server.storage.quick_slots import encode,empty

async def scenario(values,snapshot,report):
    peers=[]
    async def current():return await asyncio.to_thread(snapshot)
    try:
        before=await current();row=before[2]
        assert [r['bought']for r in before]==[0,0,1]
        assert [r['wallet']['balances']['ed']for r in before]==[25000000,25000000,24980000]
        assert eggs(row['wallet']['items'])==eggs(row['alt_items'])==1
        assert 200 not in {r['id']for r in row['achievement']['completed']}
        c=await connect(values[2],peers)
        # The native announcement is authoritative. No client wall-clock
        # predicate is needed to identify a closed server window.
        deadline=time.monotonic()+15
        while True:
            await heartbeat(c)
            if last_state(c)==0:break
            assert time.monotonic()<deadline,'Closed native sale state did not arrive'
            await asyncio.sleep(.2)
        reply=await c.query(0xea,purchase(1));assert reply.payload[:4]!=bytes(4)
        for _ in range(2):await c.query(0x6be)
        assert await current()==before
        await c.close();peers.remove(c)
        first=values[2];alt=await connect(dict(first,uid=first['alt_uid'],character_name=first['alt_name'],town=20000),peers)
        await alt.query(0x6be);saved=await current();row=saved[2]
        assert row['bought']==1 and eggs(row['alt_items'])==1
        assert row['alt_achievement']['watched']==[]and row['achievement']['watched']==[]
        binding=item_binding(710012);assert binding
        reply=await alt.query(0x8a1,struct.pack('>i',1)+encode({**empty(),0:binding}));assert reply.payload[:4]==bytes(4)
        reply=await alt.query(0x113,struct.pack('>HBBB',0,0,0,0),reply=0x114)
        assert reply.payload[:4]!=bytes(4)and eggs((await current())[2]['alt_items'])==1
        await alt.send(0x7d4,struct.pack('>ii',1,30092));reply=await alt.until(0x7d5);assert reply.payload[:4]==bytes(4)
        mode=struct.unpack_from('>i',reply.payload,4)[0]
        await alt.send(0x37f if mode==2 else 0x382,ENTRY);reply=await alt.until(0x380 if mode==2 else 0x383);assert reply.payload[:4]==bytes(4)
        await alt.until(0x14a);await alt.send(0x91,struct.pack('>ii',100,0));await alt.until(0xb2)
        await alt.send(0xb3,bytes(9));await alt.until(0xbd);await alt.query(0x48d,reply=0x48f)
        start=len(alt.received);reply=await alt.query(0x113,struct.pack('>HBBB',0,0,0,0),reply=0x114)
        assert reply.payload[:4]==bytes(4)
        effect=struct.pack('>Qi?Q?',first['alt_uid'],710012,False,0,False)
        assert sum(e.kind==0x115 and e.payload==effect for e in alt.received[start:])==1
        after=await current();assert after[2]['bought']==1 and eggs(after[2]['alt_items'])==0
        assert after[2]['wallet']==saved[2]['wallet']and after[:2]==saved[:2]
        report.update(ok=True,checks=[*report.get('checks',[]),
            'Prior public nativeC3A2 and oneEA purchase passed exact1egg/20000ED assertions before the midnight full-row comparison; committed purchase retained and not repeated',
            'Cold nativeC3A0 and closedEA refusal preserve the original one purchase; repeated6BEand cold sibling preserve history',
            'Explicit cold-role egg fixture is excluded from purchase count; normal30092admission and113use debit it once and emit one115'],
            actual_purchased_quantity=1,original_successful_purchase_reused=True,purchase_repeated=False,
            natural_spa_clock=True,native_window_states=[2,0],window_observations_span_original_and_resumed_connections=True,
            explicit_cold_role_egg_fixture=1,native_MP_effect_notification=True,natural_MP_presentation=False,
            actual_native_dungeon_admission=30092,natural_acquisition=False,native_Game=False,natural_GUI=False)
    finally:
        for p in reversed(peers):await p.close()
