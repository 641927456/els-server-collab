"""Identical native911 purchase and cold-read scenario for actual runtimes."""
import asyncio,struct,time
from achievement_protocol_client import connect
from els_server.protocol import achievement_messages as wire
from els_server.domain.achievement_catalog import points
from els_server.protocol.social_messages import wstring
from els_server.domain.town_travel import catalog


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
        invitation=struct.pack('>QIQI',values[0]['uid'],0,values[1]['uid'],0)+wstring(values[0]['character_name'])+bytes(9)
        reply=await a.query(0x5c6,invitation);assert reply.payload[:4]==bytes(4);await b.until(0x5c8)
        after=await current();assert [r['requests']for r in after]==[1,0,0]
        reply=await a.query(0x5c6,invitation);assert reply.payload[:4]!=bytes(4)
        await a.send(0x5cb,b'\0');await a.query(0x48d,reply=0x48f);await b.query(0x48d,reply=0x48f)
        after=await current();assert [r['requests']for r in after]==[1,0,0]
        #The original calendar accepts the current hour of today's selected date.
        #No production clock or stored reservation is changed.
        ends=int(time.time())//3600*3600+86340
        assert len(after[0]['ring'])==1
        raw=struct.pack('>bbQQQB',5,4,ends,values[1]['uid'],after[0]['ring'][0],0)+wstring('Owned delivery')+wstring('')+struct.pack('>bIQ',13,1,values[2]['uid'])
        reply=await a.query(0x887,raw);assert reply.payload[:4]==bytes(4)
        saved=await current();reservation=saved[0]['reservation'];assert reservation is not None
        for peer,row in zip(peers,saved):
            ids=row['wedding_mail'];assert ids
            reply=await peer.query(0x1d4,struct.pack('>I',len(ids))+b''.join(struct.pack('>Q',i)for i in ids)+bytes(6));assert reply.payload[:4]==bytes(4)
        saved=await current()
        for peer,value,row,role in zip(peers,values,saved,(2,2,1)):
            assert len(row['wedding_tickets'])==1
            reply=await peer.query(0x88b,struct.pack('>bQiB',role,row['wedding_tickets'][0],reservation,0)+wstring(''),reply=0x415)
            assert reply.payload[:4]==bytes(4)
        #A room member has no server-confirmed return yet.
        reply=await a.query(0x225,struct.pack('>iB',1500,0));assert reply.payload[:4]!=bytes(4)
        for peer,value in zip(peers,values):
            reply=await peer.query(0x417,bytes(4));assert reply.payload[:4]==bytes(4)
            town=value['town'];xyz=(0.,0.,0.)if town==1500 else catalog()['towns'][str(town)]['xyz']
            if town==1500:
                reply=await peer.query(0x225,struct.pack('>iB',20001,0));assert reply.payload[:4]!=bytes(4)
            for kind,body in((0x225,struct.pack('>iB',town,0)),(0x227,struct.pack('>fffBH',*xyz,0,0))):
                reply=await peer.query(kind,body);assert reply.payload[:4]==bytes(4),(hex(kind),town,reply.payload[:20].hex())
        #End the owned test pair through its normal free protocol, so its
        #unfinished reservation no longer remains in the public lobby source.
        for kind in(0x41a,0x41c):
            reply=await b.query(kind);assert reply.payload[:4]==bytes(4)
        await a.query(0x48d,reply=0x48f)
        closed=await current();assert not any(row['couple_current']or row['reservation_open']for row in closed)
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
            'Actual same-scene5C6invitation commits once; pending duplicate refuses and cancellation preserves history',
            'Actual887reservation, native1D4ticket mail, both spouses and guest88Badmission plus417departure restore each original scene without clock patches',
            'Premature return while still in the wedding room and arbitrary destination after departure refuse; only the server-confirmed saved1500return succeeds',
            'Normal free farewell closes the owned pair and removes its unfinished reservation from lobby eligibility',
            'Cold alternative role restores account progress with independent display and commits one separate legitimate purchase'],
            retained99_grant_level_ED_and_saved_scene_fixtures=True,natural_acquisition=False,native_Game=False,
            natural_GUI=False,production_clock_patch=False,connected_source_types=40,connected_definitions=244,
            remaining_source_types=20,unresolved_original_reward_groups=53,new_tables=0,new_indexes=0)
    finally:
        for p in reversed(peers):await p.close()
