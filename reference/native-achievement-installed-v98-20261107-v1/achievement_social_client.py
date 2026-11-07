"""Identical ordinary requests against each selected and installed runtime."""
import asyncio,struct
from achievement_protocol_client import connect
from els_server.protocol import achievement_messages as wire
from els_server.protocol.local_messages import wstring
from els_server.domain.achievement_catalog import points


async def scenario(identities,snapshot,report):
    peers=[]
    async def current():return await asyncio.to_thread(snapshot)
    async def request(p,kind,body=b'',success=True,reply=None):
        answer=await p.query(kind,body,reply)
        assert(answer.payload[:4]==bytes(4))==success,(hex(kind),answer.payload[:32].hex())
        return answer
    def notice(p,start,identity,row):
        a=row['achievement'];fresh=[r for r in a['completed']if r['id']==identity];assert len(fresh)==1
        expected=wire.completion(fresh,points(a['completed']),a['watched'],False).payload
        assert any(e.kind==0x6c0 and e.payload==expected for e in p.received[start:])
    try:
        assert len(identities)==3
        for value in identities:await connect(value,peers)
        a,b,other=peers;uid=[v['uid']for v in identities];first=identities[0]
        initial=await current()
        assert [(r['requests'],r['attempts'],r['duration'])for r in initial]==[(9,99,100),(0,0,100),(0,0,0)]
        assert all(119 in{v['id']for v in row['achievement']['completed']}for row in initial[:2])
        assert all(160 not in{v['id']for v in row['achievement']['completed']}for row in initial)
        await request(a,0x6c1,struct.pack('>i',119))
        invitation=struct.pack('>QIQI',uid[0],0,uid[1],0)+wstring(first['character_name'])+bytes(9)
        start=len(a.received);await request(a,0x5c6,invitation);await b.until(0x5c8)
        result=await current();assert result[0]['requests']==10 and all(r['requests']==0 for r in result[1:])
        notice(a,start,160,result[0])
        await request(a,0x5c6,invitation,False)
        await a.send(0x5cb,b'\0');await a.query(0x48d,reply=0x48f);await b.query(0x48d,reply=0x48f)
        assert (await current())[0]['requests']==10
        body=struct.pack('>QiiBBBBiB',first['gear_uid'],4,0,0,0,1,0,0,0)
        start=len(a.received);answer=await request(a,0x5ff,body)
        assert struct.unpack_from('>i',answer.payload,12)[0]==1
        result=await current();assert result[0]['attempts']==100
        notice(a,start,165,result[0]);await request(a,0x5ff,body,False)
        assert (await current())[0]['attempts']==100
        before=await current();await a.query(0x6be);await a.query(0x6be);assert await current()==before
        await a.close();peers.remove(a)
        # The remote read also allows normal old-connection retirement.
        await current()
        alt=await connect(dict(first,uid=first['alt_uid'],character_name=first['alt_name']),peers)
        await alt.query(0x6be)
        result=await current();shared=result[0]['alt_achievement']
        assert {119,160,165}<={r['id']for r in shared['completed']}
        assert shared['watched']==[]and result[0]['achievement']['watched']==[119]
        smith=struct.pack('>QiiBBBBiB',first['smith_gear_uid'],0,0,1,0,1,0,0,0)
        answer=await request(alt,0x5ff,smith)
        assert struct.unpack_from('>i',answer.payload,12)[0]in(1,3,4,5)
        result=await current();assert result[0]['attempts']==101
        assert all(r['attempts']==0 and r['requests']==0 for r in result[1:])
        report.update(ok=True,checks=[*report.get('checks',[]),
            'Both accounts cold-restore100full days from an explicit retained real-producer couple; foreign account has no duration',
            'Ordinary5C6saves the10th successful application and immediately notifies160only to inviter; pending duplicate fails and cancellation preserves history',
            'Ordinary full-gauge5FFsaves the100th attempt and immediately notifies165; repeating a now-invalid full-gauge request adds nothing',
            'Cold alternative role restores119/160/165with separate display and performs a real qualified blacksmith attempt; its actual unpatched outcome counts once'],
            explicit_couple_request_attempt_level_material_and_gauge_fixture=True,natural_acquisition=False,
            native_Game=False,natural_GUI=False,natural_battle=False,production_clock_patch=False,production_RNG_patch=False,
            connected_source_types=39,connected_definitions=239,remaining_source_types=21,
            unresolved_original_reward_groups=53,new_tables=0,new_indexes=1)
    finally:
        for p in reversed(peers):await p.close()
