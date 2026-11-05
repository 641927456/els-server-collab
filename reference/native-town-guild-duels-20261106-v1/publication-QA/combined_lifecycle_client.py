"""Fresh authenticated connections read only these owned duel outcomes."""
import struct
from native_peer import connect
from combined_qa_client import action,enter,leave,assets,ws

async def scenario(identities,snapshot,report):
    before=snapshot();peers=[]
    try:
        for value in identities:await connect(value,peers)
        after=snapshot();assert after==before
        assert len(after[0]['duels'])==2 and after[1]['duels']==[]and len(after[2]['duels'])==2
        assert all(r['official']is None for r in after)
        report['checks'].append('Cold authenticated login retains both zero-reward duel receipts, actual Guild membership and exact assets/quests; no official profile was created')
        a,b=identities[:2]
        answer=await peers[0].query(0x5c6,struct.pack('>QIQI',a['uid'],0,b['uid'],0)+ws(a['character_name'])+bytes(9))
        assert struct.unpack('>iQ',answer.payload)==(1680,b['uid'])and snapshot()==before
        for p in(peers[0],peers[2]):await enter(p);await leave(p)
        assert snapshot()==before
        report['checks'].append('Cold refusal still blocks without extending its receipt; both members can re-enter and leave GuildAgit after Town return')
        report['ok']=True
    finally:
        for p in reversed(peers):await p.close()
