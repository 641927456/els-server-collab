"""The same unpatched-clock public/local ceremony path for three owned accounts."""
import struct,time
from achievement_protocol_client import connect
from els_server.protocol import relationship_messages as rel,achievement_messages as wire
from els_server.protocol.social_messages import wstring
from els_server.domain.achievement_catalog import points
from els_server.domain.town_travel import catalog


async def scenario(identities,snapshot,report):
    peers=[]
    async def success(p,kind,body=b'',reply=None):
        answer=await p.query(kind,body,reply)
        assert answer.payload[:4]==bytes(4),(hex(kind),answer.payload[:20].hex())
        return answer
    def completed(row):return {r['id']for r in row['achievement']['completed']}
    def notices(p,start,fresh,row):
        a=row['achievement'];rows=[r for r in a['completed']if r['id']==fresh]
        assert len(rows)==1
        expected=wire.completion(rows,points(a['completed']),a['watched'],False).payload
        assert any(e.kind==0x6c0 and e.payload==expected for e in p.received[start:])
    try:
        assert len(identities)==3
        for value in identities:await connect(value,peers)
        groom,bride,guest=peers;uid=[v['uid']for v in identities]
        initial=snapshot();assert all(not completed(r)and r['couples']==r['ceremonies']==0 for r in initial)
        def acceptance(answer):
            return (struct.pack('>bQ',answer,uid[0])+wstring(identities[0]['character_name'])+
                struct.pack('>QBH',0,0,0)+struct.pack('>Q',uid[1])+wstring(identities[1]['character_name'])+
                bytes(1)+rel.descriptor(identities[1]['character_name']))
        async def propose():
            await success(groom,0x3fb,rel.descriptor(identities[1]['character_name']))
            await bride.until(0x3fd)
        await propose();await success(bride,0x3fe,acceptance(3))
        await groom.until(0x3ff);await groom.query(0x48d,reply=0x48f)
        assert all(not completed(r)and r['couples']==0 for r in snapshot())
        starts=[len(p.received)for p in(groom,bride)]
        await propose();await success(bride,0x3fe,acceptance(0))
        await groom.until(0x3ff);await groom.query(0x48d,reply=0x48f)
        rows=snapshot();assert [r['couples']for r in rows]==[1,1,0]
        assert [completed(r)for r in rows]==[{109},{109},set()]
        for index,p in enumerate((groom,bride)):notices(p,starts[index],109,rows[index])
        assert sum(i['count']for i in rows[0]['items']if i['template']==269710)==1
        bad=await bride.query(0x3fe,acceptance(0));assert bad.payload[:4]!=bytes(4)
        assert [r['couples']for r in snapshot()]==[1,1,0]
        await success(groom,0x6c1,struct.pack('>i',109))

        # Current-hour reservation is inside the existing stated24hour
        # window. This path patches no clock or production business function.
        ends=int(time.time())//3600*3600+86340
        ring=next(i['uid']for i in snapshot()[0]['items']if i['template']==277142)
        reserve=(struct.pack('>bbQQQB',5,4,ends,uid[1],ring,0)+wstring('Owned achievement ceremony')+
            wstring('')+struct.pack('>bIQ',13,1,uid[2]))
        await success(groom,0x887,reserve)
        rows=snapshot();reservation=rows[0]['reservation'];assert type(reservation)is int
        assert all(r['ceremonies']==0 for r in rows)
        for p,row in zip((groom,bride,guest),rows):
            ids=row['mail_ids'];assert ids
            await success(p,0x1d4,struct.pack('>I',len(ids))+b''.join(struct.pack('>Q',v)for v in ids)+bytes(6))
        rows=snapshot()
        for index,p in enumerate((groom,bride,guest)):
            ticket=next(i['uid']for i in rows[index]['items']if i['template']==(277151 if index<2 else 277152))
            join=struct.pack('>bQiB',2 if index<2 else 1,ticket,reservation,0)+wstring('')
            await success(p,0x88b,join,0x415)
        bad=await guest.query(0x41f);assert bad.payload[:4]!=bytes(4)
        await success(groom,0x41f);await bride.until(0x421)
        assert(await bride.query(0x422,bytes(2),0x423)).payload==bytes(2)
        assert all(r['ceremonies']==0 for r in snapshot())
        await success(groom,0x41f);await bride.until(0x421)
        starts=[len(p.received)for p in(groom,bride,guest)]
        await success(bride,0x422,bytes((1,0)),0x424)
        for p in(groom,guest):await p.until(0x424);await p.query(0x48d,reply=0x48f)
        rows=snapshot();assert [r['ceremonies']for r in rows]==[1,1,0]
        assert [completed(r)for r in rows]==[{109,114},{109,114},set()]
        for index,p in enumerate((groom,bride)):notices(p,starts[index],114,rows[index])
        assert not any(e.kind==0x6c0 for e in guest.received[starts[2]:])
        before=rows
        await bride.send(0x422,bytes((1,0)));await bride.query(0x48d,reply=0x48f)
        assert snapshot()==before
        for p in(groom,bride,guest):
            await success(p,0x417,bytes(4))
            await success(p,0x225,struct.pack('>iB',20001,0))
            await success(p,0x227,struct.pack('>fffBH',*catalog()['towns']['20001']['xyz'],0,0))
        before=snapshot()
        for p in(groom,bride):await p.query(0x6be);await p.query(0x6be)
        assert snapshot()==before
        await groom.close();peers.remove(groom)
        value=identities[0];alternative=dict(value,uid=value['alt_uid'],character_name=value['alt_name'])
        alt=await connect(alternative,peers);await alt.query(0x6be)
        rows=snapshot()
        assert {r['id']for r in rows[0]['alt_achievement']['completed']}=={109,114}
        assert rows[0]['alt_achievement']['watched']==[]and rows[0]['achievement']['watched']==[109]
        report.update(ok=True,completed=[sorted(completed(r))for r in rows],
            checks=['Mutual3FB/3FEacceptance consumes one owned ring and immediately completes109 for both accounts; refusal and repeated answer add none',
                'Normal887current-hour reservation, actual personalized mail claim and88Bthree-role entry run without clock patches',
                'Guest start and spouse refusal add none; actual41F/422mutual consent immediately completes114 for both spouses only',
                'Repeated consent is a silent no-op; repeated6BEis stable; alternative-character cold login shares progress and keeps independent display'],
            native_Game=False,natural_GUI=False,natural_acquisition=False,production_clock_patch=False)
    finally:
        for p in reversed(peers):await p.close()
