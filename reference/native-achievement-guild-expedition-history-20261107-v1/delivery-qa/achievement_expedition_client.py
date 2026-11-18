"""One native qualified signup, immediate notices, replay and cold account read."""
import asyncio,struct
from achievement_protocol_client import connect
from els_server.protocol import achievement_messages as wire
from els_server.domain.achievement_catalog import points


async def scenario(identities,snapshot,report):
    peers=[]
    async def current():return await asyncio.to_thread(snapshot)
    async def request(p,kind,body=b'',success=True,reply=None):
        answer=await p.query(kind,body,reply)
        assert(answer.payload[:4]==bytes(4))==success,(hex(kind),answer.payload[:32].hex())
        return answer
    def ids(row):return {r['id']for r in row['achievement']['completed']}&set(range(344,350))
    try:
        assert len(identities)==3
        for value in identities:await connect(value,peers)
        first,member,other=peers;uid=identities[0]['uid'];initial=await current()
        assert [(r['participations'],r['level'])for r in initial]==[(99,7),(0,0),(0,0)]
        assert ids(initial[0])=={347,348}and not ids(initial[1])and not ids(initial[2])
        await request(first,0x6c1,struct.pack('>i',347))
        signup=struct.pack('>bIQf',12,0x47505731,uid,1000.)
        await request(first,0xabc,signup,False)
        assert (await current())[0]['participations']==99
        for peer in(first,member):
            for kind,body,reply in((0x4fb,struct.pack('>IfffI',0,0.,0.,0.,25000),0x4fc),
                (0x225,struct.pack('>iB',25000,0),0x226),(0x504,struct.pack('>fffBH',0.,0.,0.,0,0),0x505)):
                await request(peer,kind,body,reply=reply)
        starts=[len(p.received)for p in peers];await request(first,0xabc,signup)
        await member.query(0x48d,reply=0x48f);result=await current();a=result[0]['achievement']
        assert (result[0]['participations'],result[0]['level'],result[0]['frozen_CP'])==(100,12,1000)
        assert result[0]['participating']and not result[0]['stage_cleared']and ids(result[0])==set(range(344,350))
        fresh=[r for r in a['completed']if r['id']in(344,345,346,349)];assert len(fresh)==4
        expected=wire.completion(fresh,points(a['completed']),[347],False).payload
        assert any(e.kind==0x6c0 and e.payload==expected for e in first.received[starts[0]:])
        assert all(r['participations']==r['level']==0 for r in result[1:])
        assert not any(e.kind==0x6c0 for e in member.received[starts[1]:])
        await request(first,0xabc,signup,False);await first.query(0x6be);await first.query(0x6be)
        assert await current()==result
        await first.close();peers.remove(first)
        # Ordinary reconnect after the server consumed this actor's close.
        await asyncio.sleep(.2)
        alternate=await connect(dict(identities[0],uid=identities[0]['alt_uid'],character_name=identities[0]['alt_name']),peers)
        await alternate.query(0x6be);final=await current()
        assert {r['id']for r in final[0]['alt_achievement']['completed']}&set(range(344,350))==set(range(344,350))
        assert final[0]['alt_achievement']['watched']==[]and final[0]['achievement']['watched']==[347]
        report.update(ok=True,checks=[*report.get('checks',[]),
            'Owned retained99participations atstage7; ordinary town signup refusal adds none',
            'Actual GuildAgit arrival and nativeCP1000 signup atstage12 immediately complete344/345/346/349 while stage remains uncleared',
            'Other guild member and foreign account gain no participation; repeated active signup and queries are stable',
            'Cold alternative-character login restores six account completions and separate character display'],
            explicit_guild_membership_stage_and_signup_history_fixture=True,natural_acquisition=False,
            native_Game=False,natural_GUI=False,natural_battle=False,production_clock_patch=False,
            connected_source_types=36,connected_definitions=224,remaining_source_types=24,
            unresolved_original_reward_groups=53,new_tables=0,new_indexes=0)
    finally:
        for p in reversed(peers):await p.close()
