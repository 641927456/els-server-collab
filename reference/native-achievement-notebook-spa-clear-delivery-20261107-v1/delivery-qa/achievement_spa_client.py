"""Real native purchases and cold owned-role use; no production fixture writes."""
import asyncio,struct,time
from achievement_protocol_client import connect
from els_server.domain.achievement_catalog import points
from els_server.protocol import achievement_messages as wire
from els_server.domain.quick_bindings import item_binding
from els_server.storage.quick_slots import encode,empty
ENTRY=bytes.fromhex('eefc726aad751f003e6b6d2e0c4d36e2923600000010332b6d21282a5c1774790f0f3a4c7947')

def purchase(quantity,merchant=10196):return struct.pack('>BHIiii',0,0,1,710012,quantity,merchant)
def eggs(items):return sum(i['count']for i in items if i['template']==710012)


async def heartbeat(peer):
    # The second ordinary reply also drains notices queued after the first.
    for _ in range(2):await peer.query(0x48d,reply=0x48f)


def last_state(peer):
    states=[struct.unpack('>i',e.payload)[0]for e in peer.received if e.kind==0xc3a]
    return states[-1]if states else None


async def wait_open(peer):
    start=time.monotonic()
    while time.monotonic()-start<310:
        await heartbeat(peer)
        if time.time()%300<7 and last_state(peer)==2:return time.monotonic()-start
        await asyncio.sleep(.5)
    raise TimeoutError('Natural five-minute spa sale window did not arrive')

async def scenario(values,snapshot,report):
    peers=[]
    async def current():return await asyncio.to_thread(snapshot)
    try:
        c=await connect(values[2],peers);control=await connect(values[1],peers)
        before=await current();assert all(row['bought']==0 for row in before)
        assert eggs(before[2]['wallet']['items'])==0 and eggs(before[2]['alt_items'])==1
        reply=await control.query(0xea,purchase(1));assert reply.payload[:4]!=bytes(4)
        for body in(purchase(1,10193),purchase(2),purchase(100)):
            reply=await c.query(0xea,body);assert reply.payload[:4]!=bytes(4)
        assert await current()==before
        waited=await wait_open(c)
        reply=await c.query(0xea,purchase(1));assert reply.payload[:4]==bytes(4)
        saved=await current();row=saved[2]
        assert row['bought']==1 and eggs(row['wallet']['items'])==1
        assert row['wallet']['balances']['ed']==before[2]['wallet']['balances']['ed']-20000
        assert saved[:2]==before[:2]and eggs(row['alt_items'])==1
        assert 200 not in {r['id']for r in row['achievement']['completed']}
        while time.time()%300<10:await asyncio.sleep(.2)
        await heartbeat(c);assert last_state(c)==0
        reply=await c.query(0xea,purchase(1));assert reply.payload[:4]!=bytes(4)
        for _ in range(2):await c.query(0x6be)
        assert await current()==saved
        await c.close();peers.remove(c);await current();first=values[2]
        alt=await connect(dict(first,uid=first['alt_uid'],character_name=first['alt_name'],town=20000),peers)
        await alt.query(0x6be);saved=await current();row=saved[2]
        assert 200 not in {r['id']for r in row['alt_achievement']['completed']}
        assert row['alt_achievement']['watched']==[]and row['achievement']['watched']==[]and row['bought']==1
        assert eggs(row['alt_items'])==1
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
            'Natural five-minute/ten-second window emitsC3A2 thenC3A0; one native click buys one egg for20000ED; closed window and wrong scene/seller/count refuse',
            'Repeated6BEand cold sibling preserve the account purchase quantity; one purchase does not falsely complete the500-unit achievement',
            'One explicit cold-role egg fixture does not count as a purchase; normal dungeon admission and113use debit it once and emit one115'],
            actual_purchased_quantity=1,purchased_history_fixture=False,explicit_cold_role_egg_fixture=1,
            natural_spa_clock=True,natural_window_wait_seconds=waited,native_window_states=[2,0],
            actual_native_dungeon_admission=30092,native_MP_effect_notification=True,natural_MP_presentation=False)
    finally:
        for peer in reversed(peers):await peer.close()
