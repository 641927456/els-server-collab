"""One related scenario reused against selected, public and local runtimes."""
import asyncio,struct
from achievement_protocol_client import connect
from els_server.protocol.social_messages import wstring
from els_server.protocol import achievement_messages as wire
from els_server.domain.achievement_catalog import catalog,progress_projection

async def scenario(values,snapshot,report):
    peers=[];a,b=values;uid=a['uid']
    cp_ids={i for i,d in catalog().items()if any(c['type']==17 for c in d['conditions'])}
    async def current():return await asyncio.to_thread(snapshot)
    def cp(row):
        s=row['achievement'];return dict(completed=[r for r in s['completed']if r['id']in cp_ids],
            progress=[r for r in s['progress']if r['id']in cp_ids])
    def banners(peer,start=0):return[e for e in peer.received[start:]if e.kind==0x7e2 and e.payload[:9]==struct.pack('>Q?',uid,True)]
    async def power(peer,value=None,owner=uid):
        payload=b''if value is None else struct.pack('>IQf',0x52435031,owner,value)
        answer=await peer.query(0x6be,payload);rows=await current();s=rows[0]['achievement']
        if peer is foreign:s=rows[1]['achievement']
        elif owner==a['alt_uid']:s=rows[0]['alt_achievement']
        assert answer.payload==wire.initialization([],progress_projection(s),s['completed'],s['watched']).payload
        return rows
    async def enter(peer):
        for kind,body,answer in((0x4fb,struct.pack('>IfffI',0,0.,0.,0.,25000),0x4fc),
            (0x225,struct.pack('>iB',25000,0),0x226),(0x504,struct.pack('>fffBH',0.,0.,0.,0,0),0x505)):
            assert(await peer.query(kind,body,answer)).payload[:4]==bytes(4)
    try:
        baseline=await current();p=await connect(a,peers);foreign=None
        assert cp((await power(p))[0])==dict(completed=[],progress=[])
        assert(await p.query(0x276,struct.pack('>Q',a['license_uid'])+wstring('CPG'+str(uid))+wstring('Owned banner and power qualification'))).payload[:4]==bytes(4)
        after_create=await current();expected=baseline[0]['economy'][str(uid)]['items']
        assert after_create[0]['economy'][str(uid)]['items']==[i for i in expected if i['uid']!=a['license_uid']]
        assert after_create[0]['economy'][str(uid)]['balance']==baseline[0]['economy'][str(uid)]['balance']
        for n in range(10):
            if n:assert(await p.query(0x7e0,b'\0')).payload==bytes(4)
            assert(await p.query(0x7e0,b'\1')).payload==bytes(4)
        rows=await current();assert rows[0]['banner_count']==10
        assert 350 in{r['id']for r in rows[0]['achievement']['completed']}
        foreign=await connect(b,peers);assert len(banners(foreign))==1
        marker=len(foreign.received);assert(await p.query(0x6c1,struct.pack('>I',350))).payload[:4]==bytes(4)
        await foreign.query(0x48d,reply=0x48f)
        assert any(e.kind==0x22a for e in foreign.received[marker:])and len(banners(foreign,marker))==1
        assert(await p.query(0x285,wstring(b['character_name'])+struct.pack('>Q',b['uid']))).payload[:4]==bytes(4)
        guild=(await current())[0]['guild_id'];assert guild
        assert(await foreign.query(0x288,struct.pack('>i',guild)+wstring(a['character_name'])+bytes(4))).payload[:4]==bytes(4)
        await enter(p);assert(await p.query(0x7e0,b'\1')).payload==bytes(4)
        marker=len(foreign.received);await enter(foreign);assert len(banners(foreign,marker))==1
        marker=len(foreign.received);assert(await p.query(0x6c1,struct.pack('>I',350))).payload[:4]==bytes(4)
        await foreign.query(0x48d,reply=0x48f)
        assert any(e.kind==0x4fd for e in foreign.received[marker:])and len(banners(foreign,marker))==1
        assert(await p.query(0x7e0,b'\0')).payload==bytes(4)
        marker=len(foreign.received);assert(await p.query(0x6c1,struct.pack('>I',350))).payload[:4]==bytes(4)
        await foreign.query(0x48d,reply=0x48f);assert not banners(foreign,marker)
        assert(await current())[0]['banner_count']==11
        report['checks'].append('11 accepted guild banner summons;4actual late/rebuilt actor paths;withdrawal excluded;state restoration does not increment')
        rows=await power(p,4199);assert cp(rows[0])['completed']==[]
        assert{r['id']:r['conditions'][0]['count']for r in cp(rows[0])['progress']}=={85:4199,86:4199}
        rows=await power(p,4200);assert{r['id']for r in cp(rows[0])['completed']}=={85}
        rows=await power(p,7000);assert{r['id']for r in cp(rows[0])['completed']}=={85,86};attained=cp(rows[0])
        for value in(None,1,4294967040,7000):assert cp((await power(p,value))[0])==attained
        assert cp((await power(foreign))[1])==dict(completed=[],progress=[])
        await p.close();peers.remove(p);await current()
        alt=dict(a,uid=a['alt_uid'],character_name=a['alt_name'])
        p=await connect(alt,peers);assert cp((await power(p,owner=a['alt_uid']))[0])==attained
        rows=await power(p,7000,a['alt_uid']);assert{r['id']for r in cp(rows[0])['completed']}=={85,86,87,88};attained=cp(rows[0])
        await p.close();peers.remove(p);await current();p=await connect(a,peers)
        rows=await power(p);assert cp(rows[0])==attained and rows[0]['banner_count']==11
        assert rows[0]['economy']==after_create[0]['economy']and rows[1]['economy']==baseline[1]['economy']
        report['checks'].append('CP4199/4200/7000;lower/bare/replay/huge keep history;2families account shared;cold primary restores;foreign isolated;economy unchanged after license use')
        report.update(ok=True,connected_source_types=47,connected_definitions=318,remaining_source_types=13,
            unresolved_original_reward_groups=53,new_tables=0,new_indexes=0,
            natural_GUI=False,native_Game=False,natural_battle=False,natural_acquisition=False,
            native_CP_values='Explicit trusted-source payload fixtures; real native arithmetic separately qualified',
            owned_level_ED_license_fixtures=True,production_clock_patch=False)
    finally:
        for peer in reversed(peers):await peer.close()
