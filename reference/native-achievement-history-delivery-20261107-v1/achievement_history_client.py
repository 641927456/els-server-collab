"""The same finite native-request scenario runs against private, public and local."""
import asyncio,struct
from achievement_protocol_client import connect
from els_server.protocol.local_messages import wstring


def ids(row):return {r['id']for r in row['achievement']['completed']}
def allocation(delta):return struct.pack('>IBIiiB',1,0,1,1,delta,1)


async def scenario(identities,snapshot,report,prime):
    peers=[]
    async def request(peer,kind,body=b'',success=True):
        answer=await peer.query(kind,body)
        assert(answer.payload[:4]==bytes(4))==success,(hex(kind),answer.payload[:24].hex())
        return answer
    try:
        a,b,c=[await connect(identity,peers)for identity in identities]
        initial=snapshot();baseline=ids(initial[0]);assert baseline=={73,74,75}and not ids(initial[1])and not ids(initial[2])
        money=initial[0]['money']
        await request(a,0x611,allocation(100));await request(a,0x611,allocation(-100));await request(a,0x611,allocation(-1),False)
        for _ in range(5):
            await request(a,0x611,allocation(1));await request(a,0x613,bytes((0,1)))
        await request(a,0x613,bytes((0,1)),False)
        # Initial fixture may contain singleton or stack readers. Use the
        # actual still-owned source from the last authoritative readback.
        remaining={i['uid']:i['count']for i in initial[0]['items']if i['template']==189800}
        assert sum(remaining.values())==5
        for _ in range(5):
            uid=next(uid for uid,count in remaining.items()if count)
            await request(a,0x718,struct.pack('>QiB',uid,2,1));remaining[uid]-=1
        await request(a,0x718,struct.pack('>QiB',uid,2,1),False)
        consumed=snapshot();resonance={78,80,81,82,83,84,299,300}
        assert ids(consumed[0])==baseline|resonance and consumed[0]['money']['ed']==money['ed']and consumed[0]['money']['experience']==money['experience']
        assert not any(i['template']in(710106,163564,189800)for i in consumed[0]['items'])
        fixture=identities[0]['fixture']
        await request(a,0x276,struct.pack('>Q',fixture['license_uid'])+wstring('AH'+str(identities[0]['uid']))+wstring('Owned history QA'))
        guild=snapshot()[0]['guild'];assert type(guild)is int and guild>0
        for peer,identity in((b,identities[1]),(c,identities[2])):
            await request(a,0x285,wstring(identity['character_name'])+struct.pack('>Q',identity['uid']))
            await peer.query(0x48d,reply=0x48f)
            await request(peer,0x288,struct.pack('>i',guild)+wstring(identities[0]['character_name'])+struct.pack('>i',0))
        await request(b,0x290,struct.pack('>QB',identities[1]['uid'],0));await request(b,0x290,struct.pack('>QB',identities[1]['uid'],0),False)
        await request(a,0x290,struct.pack('>QB',identities[2]['uid'],1))
        left=snapshot();assert ids(left[1])=={130}and not ids(left[2])and ids(left[0])==baseline|resonance
        await request(a,0x4fb,struct.pack('>IfffI',0,0.,0.,0.,25000));await request(a,0x504,struct.pack('>fffBH',0.,0.,0.,0,0))
        await request(a,0x7fd,struct.pack('>iQ',1,fixture['seed_uid']))
        assert prime()['ok'];await a.query(0x6be)
        await request(a,0x27d,bytes((1,))+wstring('Owned native board post'))
        await request(a,0x803,struct.pack('>i',1));await request(a,0x803,struct.pack('>i',1),False)
        await request(a,0x27d,bytes((1,))+wstring(' '),False)
        await request(a,0x28e,wstring('Separate owned announcement'));await request(a,0x6a9,struct.pack('>Q',1))
        expected=baseline|resonance|{140,145,338};after=snapshot();assert ids(after[0])==expected
        assert sum(i['count']for i in after[0]['items']if i['template']==fixture['crop_template'])==fixture['crop_quantity']
        for _ in range(2):
            answer=await a.query(0x6c9,struct.pack('>i',338));assert answer.payload[:4]==struct.pack('>i',2005)
            await a.query(0x6be)
        repeat=snapshot();assert repeat[0]['achievement']==after[0]['achievement']and repeat[0]['operations']==after[0]['operations']
        await request(a,0x6c1,struct.pack('>i',145));await a.close();peers.remove(a)
        # Snapshot is a real writer/connection scheduling boundary in public
        # use; no player input or process control is involved.
        snapshot();await asyncio.sleep(.1)
        alt=await connect(identities[0]['alt'],peers);await alt.query(0x6be)
        final=snapshot();assert ids(final[3])==ids(final[0])==expected
        assert final[0]['achievement']['watched']==[145]and final[3]['achievement']['watched']==[]
        assert ids(final[1])=={130}and not ids(final[2])
        report.update(ok=True,checks=[
            'Three enrolled accounts use pinned TLS and ordinary town entry; ERP150fixture restores73through75only for its owner',
            'Ordinary611/613transactions consume100coins and5scrolls; five718mentor uses consume5owned units; rejected repeats add no completions or ED/XP',
            'Ordinary guild creation/invitation/join establishes real membership; voluntary departure completes130once while master expulsion gives neither actor a departure completion',
            'Ordinary GuildAgit entry and planting precede finite retained-history/maturity fixtures; one real post and harvest complete145,338and140',
            'Failed empty harvest/post, announcement edit and post deletion add no history count; repeated missing-original reward claim338stays deferred',
            'Repeated6BEadds no achievement operation; alternative-character cold login shares all14completions and preserves separate display lists'],
            natural_GUI=False,natural_acquisition=False,natural_growth_wait=False,natural_battle=False,
            fixture_accounts=3,fixture_characters=4,connected_source_types=21,connected_definitions=136,unresolved_original_reward_groups=53)
    finally:
        for peer in peers:await peer.close()
