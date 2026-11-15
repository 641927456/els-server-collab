"""Finite ordinary requests shared by actual signed, public and local acceptance."""
import asyncio,struct
from achievement_protocol_client import connect


def ids(row):return {r['id']for r in row['achievement']['completed']}


def completed(peer):
    values=[]
    for event in peer.received:
        if event.kind!=0x6c0:continue
        n=struct.unpack_from('>I',event.payload)[0];offset=4
        for _ in range(n):
            identity,length=struct.unpack_from('>iI',event.payload,offset)
            offset+=8+length+1;values.append(identity)
    return values


async def scenario(identities,snapshot,report,prime=None):
    peers=[]
    async def request(peer,kind,body=b'',success=True):
        reply=await peer.query(kind,body)
        assert(reply.payload[:4]==bytes(4))==success,(hex(kind),reply.payload[:24].hex())
        return reply
    try:
        a,b,c=[await connect(identity,peers)for identity in identities]
        initial=snapshot();assert not any(ids(row)for row in initial)
        f=identities[0]['fixture']
        await request(a,0x5ff,struct.pack('>QiiBBBBiB',f['gear'],4,0,0,0,1,0,0,0))
        batch=struct.pack('>QI',f['socket_target'],2)+b''.join(struct.pack('>iQ',slot,f['stone'])for slot in(0,1))+struct.pack('>BBI6i',0,0,6,*([0]*6))
        await request(a,0x1c4,batch)
        await request(a,0x6e7,struct.pack('>QIiIiQBiB',f['weapon'],1,10,1,0,f['mystic'],0,2,0))
        preview=snapshot()[0];assert preview['history']['(60, 0)']==100
        await request(a,0x6e7,struct.pack('>QIBiB',f['weapon'],0,0,4,0))
        applied=snapshot()[0]
        assert applied['history']['(60, 0)']==100 and applied['money']==preview['money']
        await request(a,0x705,struct.pack('>i',117527))
        await request(a,0x1c4,batch,False);await request(a,0x705,struct.pack('>i',117527),False)
        await request(b,0x9b3);await request(b,0x9b3,success=False)
        body=struct.pack('>I5Q',5,*identities[2]['fixture']['ingredients'])
        await request(c,0x707,body);await request(c,0x707,body,False)
        money=snapshot()[0]['money']
        await request(a,0x113,struct.pack('>HBBB',5,0,0,0),False)
        await request(a,0x7d4,struct.pack('>ii',1,30000))
        await request(a,0x382,bytes.fromhex('eefc726aad751f003e6b6d2e0c4d36e2923600000010332b6d21282a5c1774790f0f3a4c7947'))
        await request(a,0x91,struct.pack('>ii',100,0));await request(a,0xb3,bytes(9))
        await request(a,0x113,struct.pack('>HBBB',5,0,0,0))
        await request(a,0x113,struct.pack('>HBBB',5,0,0,0),False)
        owner=identities[0]['uid'];revive=struct.pack('>?QQ?',False,0,owner,False)
        await request(a,0x160,revive,False)
        death=struct.pack('>iQQBffi?',-1,owner,owner,0,0,0,-1,False)
        answer=await a.query(0xa7,death);assert answer.payload[4:8]==bytes(4)
        await a.query(0xaa,reply=0xac);await request(a,0x160,revive);await request(a,0x160,revive,False)
        assert completed(a)==[185,205,355,304,210,235]and completed(b)==[309]and completed(c)==[314]
        current=snapshot();expected=[{185,205,210,235,304,355},{309},{314}]
        assert [ids(r)for r in current[:3]]==expected
        assert current[0]['history']=={'(32, 10)':5,'(35, 4)':1000,'(36, 0)':100,'(45, 0)':1000,'(51, 0)':100,'(52, 0)':0,'(53, 0)':0,'(60, 0)':100}
        assert current[0]['money']==money,'Potion use or owned-stone revival charged unexpected ED/XP'
        assert current[1]['history']['(53, 0)']==10 and current[2]['history']['(52, 0)']==100
        assert not any(i['template']in(77010,135184,136109,117527)for i in current[0]['items'])
        await request(a,0x6c1,struct.pack('>i',185))
        for peer,identity in((b,309),(c,314)):
            before=snapshot()
            for _ in range(2):
                reply=await peer.query(0x6c9,struct.pack('>i',identity))
                assert struct.unpack_from('>i',reply.payload)[0]==2005
            assert snapshot()==before,'Missing original reward changed persisted QA state'
        for peer in(a,b,c):await peer.query(0x6be)
        before=snapshot()
        for peer in(a,b,c):await peer.query(0x6be)
        assert snapshot()==before
        await a.close();peers.remove(a)
        # The normal barrier round-trip lets the departing lease drain before
        # the same account enters on its alternative character.
        await b.query(0x6be)
        alt=await connect(identities[0]['alt'],peers);await alt.query(0x6be)
        final=snapshot();assert ids(final[3])==expected[0]
        assert final[0]['achievement']['watched']==[185] and final[3]['achievement']['watched']==[]
        assert not any(r['received']for row in final for r in row['achievement']['completed'])
        report.update(ok=True,completed=[sorted(ids(r))for r in final],
            checks=['Eight actual sources cross their thresholds with immediate6C0notifications',
                'Two-slot batch counts two; paid mystic preview/apply counts one with no second fee',
                'Normal isolated dungeon entry, actual potion use and death-confirmed owned-stone revival complete210/235',
                'No-material and cooldown failures add no count; accounts remain isolated',
                'Missing original anvil/flask rewards refused twice without received markers or payment',
                'Repeated query is stable; alternative-character cold login shares progress and keeps independent display'],
            native_Game=False,natural_GUI=False,natural_acquisition=False)
    finally:
        for peer in peers:await peer.close()
