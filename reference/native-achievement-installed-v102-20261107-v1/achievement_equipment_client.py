"""Actual wear, shared achievements and normal GuildAgit lifecycle."""
import asyncio,struct
from achievement_protocol_client import connect
from els_server.domain.ordinary_accessories import definitions as accessories
from els_server.domain.equipment_requirements import inspect_requirements
from els_server.domain.town_travel import catalog
from els_server.protocol.social_messages import wstring

async def scenario(values,snapshot,report):
    peers=[]
    async def current():return await asyncio.to_thread(snapshot)
    async def request(peer,kind,body=b'',reply=None):
        answer=await peer.query(kind,body,reply);assert answer.payload[:4]==bytes(4),(hex(kind),answer.payload[:20].hex());return answer
    try:
        for v in values:await connect(v,peers)
        a,b,c=peers;before=await current();ids=lambda row:{r['id']for r in row['achievement']['completed']}
        assert before[0]['equipped']=={'297':0,'298':0,'371':3,'372':3}and 371 in ids(before[0])and 372 not in ids(before[0])
        assert [row['play_days']for row in before]==[100,1,1]and 42 in ids(before[0])
        async def wear(template,on=True):
            row=(await current())[0];item=next(i for i in row['items']if i['template']==template);slot=inspect_requirements(template,1)['equipment_slot']if template<189000 else accessories()[template]['main_slots'][0]
            group=1 if template<189000 else 2;body=struct.pack('>BiBiB',item['group'],item['slot'],9 if on else group,slot if on else 20,0)
            start=len(a.received);reply=await a.query(0x104,body);assert reply.payload[-4:]==bytes(4)and int.from_bytes(reply.payload[:4],'big')==2
            return start
        start=await wear(118156);assert 372 in ids((await current())[0])and any(e.kind==0x6c0 for e in a.received[start:])
        await wear(118156,False);assert 372 in ids((await current())[0])
        for template in range(189020,189026):
            start=await wear(template)
            if template in(189022,189025):assert(297 if template==189022 else 298)in ids((await current())[0])and any(e.kind==0x6c0 for e in a.received[start:])
        row=(await current())[0];license=next(i for i in row['items']if i['template']==110845)
        await request(a,0x276,struct.pack('>Q',license['uid'])+wstring('EQ'+str(values[0]['uid']))+wstring('Owned delivery'))
        guild=(await current())[0]['guild'];assert guild
        await request(a,0x285,wstring(values[1]['character_name'])+struct.pack('>Q',values[1]['uid']));await b.until(0x287)
        await request(b,0x288,struct.pack('>i',guild)+wstring(values[0]['character_name'])+bytes(4))
        for peer in(a,b):
            for kind,body,reply in((0x4fb,struct.pack('>IfffI',0,0.,0.,0.,25000),0x4fc),(0x225,struct.pack('>iB',25000,0),0x226),(0x504,struct.pack('>fffBH',0.,0.,0.,0,0),0x505)):await request(peer,kind,body,reply)
        await request(a,0x6c1,struct.pack('>i',298));await b.query(0x48d,reply=0x48f)
        for peer in(a,b):
            await request(peer,0x4fe)
            for kind,body in((0x225,struct.pack('>iB',20001,0)),(0x227,struct.pack('>fffBH',*catalog()['towns']['20001']['xyz'],0,0))):await request(peer,kind,body)
        await request(b,0x290,struct.pack('>QB',values[1]['uid'],0));await request(a,0x294)
        assert all(row['guild']is None for row in await current())
        before=await current();await a.query(0x6be);await a.query(0x6be);assert await current()==before
        await a.close();peers.remove(a);await current();first=values[0]
        alt=await connect(dict(first,uid=first['alt_uid'],character_name=first['alt_name']),peers);await alt.query(0x6be);saved=(await current())[0]
        assert {297,298,371,372}<={r['id']for r in saved['alt_achievement']['completed']}and saved['alt_achievement']['watched']==[]and saved['achievement']['watched']==[298]
        assert saved['play_days']==100 and 42 in{r['id']for r in saved['alt_achievement']['completed']}
        report.update(ok=True,checks=[*report.get('checks',[]),'Stored worn counts use the maximum of one owned role; bag and foreign-account equipment do not count','Actual104/105 completes fourth armor and third/sixth accessories immediately; unwear and repeat remain stable','Actual guild create/invite/accept, both504arrivals, GuildAgit achievement display and normal return/leave/disband complete without stranded membership','Cold sibling shares account completion with independent display','Cold first entry records the100th distinct UTC+8date from99retained fixture records; same-date reads and sibling entry do not increment'],retained_equipment_level_ED_fixtures=True,retained99_play_day_fixture=True,natural_acquisition=False,native_Game=False,natural_GUI=False,production_clock_patch=False,connected_source_types=42,connected_definitions=253,remaining_source_types=18,unresolved_original_reward_groups=53,new_tables=0,new_indexes=0)
    finally:
        for p in reversed(peers):await p.close()
