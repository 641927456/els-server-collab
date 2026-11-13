"""Check successful attendance and each affected live refusal over owned TLS."""
import asyncio,ipaddress,struct
from protocol_harness import Peer,enter
from els_server.friends_bridge import Bridge,BridgeConfig

TEXTS={717:'签到失败。',3025:'未激活签到。',3026:'今天已完成签到。',3027:'补签道具使用失败。',3029:'无法补签。',3022:'已领取奖励。',1919:'选择了无法领取的累计签到奖励。'}

async def check(rows,*,runtime,progress,require_public=True,phase='test'):
    peers=[];observed=[]
    async def attendance(peer,kind,expected=0,index=None,body=None):
        payload=body if body is not None else struct.pack('>i',3)+(struct.pack('>i',index)if index is not None else b'')
        reply=await peer.request(kind,payload,kind+1)
        assert len(reply.payload)==4 and struct.unpack('>i',reply.payload)==(expected,),(kind,reply.payload.hex())
        if expected:observed.append(expected)
    try:
        for row in rows:
            if require_public:assert ipaddress.ip_address(row['bridge']['host']).is_global
            peer=await Peer.open(Bridge(BridgeConfig(**row['bridge'])));peers.append(peer);await enter(peer,row['uid'],town=row['town']if phase=='test'else 1500)
        a,b=peers
        if phase=='test':
            await attendance(a,0xc8c,3025)
            await a.request(0x80d,struct.pack('>i',1),0x80e)
            activation=await a.request(0x80f,struct.pack('>IIH',1,1200721049,1),0x810)
            assert activation.payload[:4]==bytes(4)
            await attendance(a,0xc8e,1919,index=0)
            await attendance(a,0xc8c)
            await attendance(a,0xc8c,3026)
            await attendance(a,0xc8e,index=0)
            await attendance(a,0xc8e,3022,index=0)
            await attendance(a,0xc90,3029)
            await attendance(a,0xc8c,717,body=b'bad')
            await attendance(b,0xc90)
            await attendance(b,0xc8c)
            await attendance(b,0xc8e,index=0)
            await attendance(b,0xc8e,3022,index=0)
            await attendance(b,0xc90,3027)
            cases=['50 ED activation, attendance and one reward; makeup consumes its coupon; specific refusal codes preserve final counts']
            async def ok(peer,kind,body,response,code=0):
                reply=await peer.request(kind,body,response)
                assert struct.unpack_from('>i',reply.payload)[0]==code,(hex(kind),reply.payload[:4].hex())
                return reply
            for peer in peers:
                await ok(peer,0x225,struct.pack('>iB',1500,1),0x226)
                await ok(peer,0x227,struct.pack('>3fBH',1.,2.,3.,0,0),0x228)
            await ok(b,0x8b4,b'',0x8b5,2306)
            await ok(b,0x219,struct.pack('>Q',rows[1]['vip'])+bytes(21),0x21a,2307)
            await ok(a,0xee,struct.pack('>ii',25600,10025),0xef)
            await ok(a,0xfd,struct.pack('>i',7507),0xfe)
            await ok(a,0xf4,struct.pack('>iiI5B',25600,0,0,0,0,1,1,0),0xf5)
            await ok(a,0xee,struct.pack('>ii',25601,10025),0xef)
            await ok(a,0x8b4,b'',0x8b5)
            progress('owned-fishing-cycle-started',cases=cases)
            await asyncio.sleep(36)
            notice=await a.until(0x8b8)
            assert len(notice.payload)>=13 and struct.unpack_from('>i?I',notice.payload)[0::2]==(0,2)
            consumed=dict(struct.unpack_from('>Qi',notice.payload,9+12*i)for i in range(2))
            assert consumed=={rows[0]['bait']:9,rows[0]['rod']:9960}
            await ok(a,0x8b6,b'',0x8b7)
            await ok(a,0x51c,struct.pack('>ii',40256,0),0x51d)
            await ok(a,0x223,struct.pack('>iQiiiiiBi',40256,0,135937,10,135949,3,1,1,0),0x224)
            await ok(a,0x18c,struct.pack('>IQBBi',1,rows[0]['rod'],0,0,0),0x18d)
            cases.append('Held theme rod real timed settlement, repair, fish exchange and account-bound teaching followup; full life bag and exhausted VIP reject')
        else:
            for i,peer in enumerate(peers):
                status=next(e for e in reversed(peer.events)if e.kind==0xc89)
                assert struct.unpack_from('>i',status.payload,9)[0]+1==(1 if i==0 else 2)
                assert struct.unpack_from('>i',status.payload,17)[0]==1
            cases=['Both accounts cold login with the expected attendance and reward flags']
        progress('public-requests-complete-awaiting-cold-read',cases=cases)
        return dict(ok=True,phase=phase,public_network=require_public,actual_TLS=True,cases=cases,native_error_codes=observed,native_lookup_texts={str(k):TEXTS[k]for k in sorted(set(observed))},natural_GUI=False,natural_battle=False)
    finally:
        for peer in peers:await peer.close()
