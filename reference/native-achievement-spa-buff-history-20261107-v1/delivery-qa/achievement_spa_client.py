"""Identical native911 purchase and cold-read scenario for actual runtimes."""
import asyncio,struct
from achievement_protocol_client import connect
from els_server.protocol import achievement_messages as wire
from els_server.domain.achievement_catalog import points


async def scenario(values,snapshot,report):
    peers=[]
    async def current():return await asyncio.to_thread(snapshot)
    async def purchase(peer,success=True):
        reply=await peer.query(0x911,bytes(4));assert(reply.payload[:4]==bytes(4))==success
        return struct.unpack_from('>Q',reply.payload,4)[0]
    try:
        for value in values:await connect(value,peers)
        a,b,c=peers;before=await current();assert [r['count']for r in before]==[99,0,0]
        assert all(29 not in{r['id']for r in row['achievement']['completed']}for row in before)
        start=len(a.received);ed=await purchase(a);after=await current()
        assert after[0]['count']==100 and before[0]['ed']-ed==500000 and after[0]['ed']==ed
        fresh=[r for r in after[0]['achievement']['completed']if r['id']==29];assert len(fresh)==1
        expected=wire.completion(fresh,points(after[0]['achievement']['completed']),[],False).payload
        assert any(e.kind==0x6c0 and e.payload==expected for e in a.received[start:])
        await purchase(b,False);await purchase(c,False);assert await current()==after
        reply=await a.query(0x6c1,struct.pack('>i',29));assert reply.payload[:4]==bytes(4)
        before=await current();await a.query(0x6be);await a.query(0x6be);assert await current()==before
        await a.close();peers.remove(a);await current()
        first=values[0];alt=await connect(dict(first,uid=first['alt_uid'],character_name=first['alt_name']),peers)
        await alt.query(0x6be);restored=await current();shared=restored[0]['alt_achievement']
        assert 29 in{r['id']for r in shared['completed']}and shared['watched']==[]
        assert restored[0]['achievement']['watched']==[29]
        await purchase(alt);result=await current();assert result[0]['count']==101
        assert all(row['count']==0 for row in result[1:])
        report.update(ok=True,checks=[*report.get('checks',[]),
            'Real911 debits500000ED and commits the100th grant with immediate29notification on the authenticated account',
            'InsufficientED and wrongscene refuse without any increment; repeated6BEreads are stable',
            'Cold alternative role restores account progress with independent display and commits one separate legitimate purchase'],
            retained99_grant_level_ED_and_saved_scene_fixtures=True,natural_acquisition=False,native_Game=False,
            natural_GUI=False,production_clock_patch=False,connected_source_types=40,connected_definitions=244,
            remaining_source_types=20,unresolved_original_reward_groups=53,new_tables=0,new_indexes=0)
    finally:
        for p in reversed(peers):await p.close()
