"""Same explicit App/TLS official match and41400 clear on every delivery."""
import asyncio,json,struct,uuid
from achievement_protocol_client import connect
from achievement_pvp_fixture import registration
from els_server.domain.pvp_support import SOURCE_SHA
from els_server.friends_relay import read_packet
from els_server.protocol import achievement_messages as wire
from els_server.domain.achievement_catalog import points
from els_server.domain.town_travel import catalog
from els_server.domain.dungeon_npcs import MODE0_FIELDS


def hp(value):
    raw=bytearray(182);struct.pack_into('>f',raw,0,value)
    return bytes(raw)+b'PVP1'+struct.pack('>f',1000.)


def population(event):
    """Read the admitted native mode0 spawn prefix, not a constructed run."""
    raw=event.payload;stage=struct.unpack_from('>i',raw)[0];offset=8
    parts=struct.unpack_from('>I',raw,offset)[0];offset+=4;result=[]
    assert parts==1
    for _ in range(parts):
        part,opaque,count=struct.unpack_from('>iII',raw,offset);offset+=12
        assert part==opaque==0 and 1<=count<=8
        for _ in range(count):
            fields={}
            for off,size,key,kind in MODE0_FIELDS:
                value=int.from_bytes(raw[offset:offset+size],'big');offset+=size
                if kind=='empty':assert value==0
                else:fields[off]=value^key
            result.append(dict(key=fields[0],template=fields[4],active=bool(fields[0x4e]),hp=1000.))
    return stage,result


def death(npc,owner):
    # The retained41400 prototype accepts authenticated reports; this is an
    # explicit positive death-report scalar, not a natural damage claim.
    return (struct.pack('>iBQQ6fBf',npc['key'],0,owner,owner,0.,0.,0.,0.,0.,0.,0,npc['hp'])
        +bytes(8)+struct.pack('>Q',0)+bytes(4)+struct.pack('>Q',owner))


async def support_fixture(peer):
    reader,writer=await peer.bridge.remote(role='relay')
    def send(body):writer.write(struct.pack('>I',len(body))+body)
    send(b'\7'+json.dumps(dict(version=1,ready=True,epoch=str(uuid.uuid4()),source_sha256=SOURCE_SHA)).encode())
    send(b'\3'+struct.pack('>Q',1));await writer.drain()
    # Ordered heartbeat proves this authenticated status was consumed.
    async with asyncio.timeout(10):
        while await read_packet(reader)!=b'\4'+struct.pack('>Q',1):pass
    async def heartbeats():
        counter=1
        while True:
            await asyncio.sleep(5);counter+=1;send(b'\3'+struct.pack('>Q',counter));await writer.drain()
    async def drain():
        while True:await read_packet(reader)
    return writer,[asyncio.create_task(heartbeats()),asyncio.create_task(drain())]


async def scenario(identities,snapshot,report):
    peers=[];relays=[]
    async def success(p,kind,body=b'',reply=None):
        answer=await p.query(kind,body,reply)
        assert answer.payload[:4]==bytes(4),(hex(kind),answer.payload[:20].hex())
        return answer
    async def seen(p,kind,start=0):
        old=next((e for e in p.received[start:]if e.kind==kind),None)
        return old if old is not None else await p.until(kind)
    def completed(row):return {r['id']for r in row['achievement']['completed']}
    def notice(p,start,fresh,row):
        a=row['achievement'];rows=[r for r in a['completed']if r['id']in fresh];assert len(rows)==len(fresh)
        expected=wire.completion(rows,points(a['completed']),a['watched'],False).payload
        assert any(e.kind==0x6c0 and e.payload==expected for e in p.received[start:])
    try:
        assert len(identities)==3
        for value in identities:await connect(value,peers)
        a,b,timed=peers;uid=[v['uid']for v in identities]
        initial=snapshot();assert all(not completed(r)and r['best']is None for r in initial)
        assert [(r['wins'],r['losses'])for r in initial]==[(99,99),(99,99),(0,0)]
        for p in(a,b):relays.append(await support_fixture(p))
        for p in(a,b):await success(p,0x7d4,struct.pack('>ii',5,30000));await success(p,0x342,registration())
        for p in(a,b):await seen(p,0x349)
        for p in(a,b):await p.send(0x34a,b'\1\1\0'+bytes(4)+b'\0')
        for p in(a,b):await p.until(0x34b)
        for p in(a,b):await success(p,0x91,struct.pack('>ii',100,0))
        for p in(a,b):await seen(p,0x96)
        assert snapshot()==initial
        dying=struct.pack('>iQQBffi?',-1,uid[0],uid[0],0,0.,0.,-1,False)
        ack=await b.query(0xa7,dying);assert ack.payload[4:8]==bytes(4)
        await b.send(0xaa)
        for p in(a,b):await p.until(0x9d)
        assert snapshot()==initial
        starts=[len(p.received)for p in(a,b)]
        await success(a,0x9e,hp(1000.));await success(b,0x9e,hp(0.))
        for index,p in enumerate((a,b)):await seen(p,0xc2,starts[index]);await p.query(0x48d,reply=0x48f)
        rows=snapshot();assert [completed(r)for r in rows]==[{13},{16},set()]
        assert [(r['wins'],r['losses'])for r in rows]==[(100,99),(99,100),(0,0)]
        for index,identity in((0,13),(1,16)):notice(peers[index],starts[index],{identity},rows[index])
        assert not any(e.kind==0x6c0 for e in timed.received)
        before=rows
        for p,identity,value in((a,13,1000.),(b,16,0.)):
            await success(p,0x9e,hp(value))
            for _ in range(2):
                denied=await p.query(0x6c9,struct.pack('>i',identity));assert denied.payload[:4]==struct.pack('>i',2005)
            await success(p,0x67,struct.pack('>i',0)+hp(value)+bytes(4))
            await success(p,0x225,struct.pack('>iB',20001,0))
            await success(p,0x227,struct.pack('>fffBH',*catalog()['towns']['20001']['xyz'],0,0))
            await p.query(0x6be);await p.query(0x6be)
        assert snapshot()==before
        await success(a,0x6c1,struct.pack('>i',13))
        await a.close();peers.remove(a)
        value=identities[0];alt=await connect(dict(value,uid=value['alt_uid'],character_name=value['alt_name']),peers)
        await alt.query(0x6be);rows=snapshot()
        assert {r['id']for r in rows[0]['alt_achievement']['completed']}=={13}
        assert rows[0]['alt_achievement']['watched']==[]and rows[0]['achievement']['watched']==[13]

        await success(timed,0x7d4,struct.pack('>ii',2,41400))
        opaque=bytes.fromhex('eefc726aad751f003e6b6d2e0c4d36e2923600000010332b6d21282a5c1774790f0f3a4c7947')
        await success(timed,0x37f,opaque)
        await success(timed,0x91,struct.pack('>ii',100,0));await success(timed,0xb3,bytes(9))
        assert snapshot()[2]['best']is None
        await asyncio.sleep(1.1);stages=[];last=None
        for step in range(4):
            event=next(e for e in reversed(timed.received)if e.kind==0xb2)
            stage,npcs=population(event);stages.append(stage)
            for npc in npcs:
                if npc['active']:last=death(npc,uid[2]);await success(timed,0xad,last)
            if step<3:assert snapshot()[2]['best']is None and not completed(snapshot()[2])
            start=len(timed.received);await success(timed,0xbb,bytes(1))
            if step<3:await success(timed,0xb3,bytes(9))
        assert set(stages)=={0,1,2,3}and len(stages)==4
        rows=snapshot();seconds=rows[2]['best'];assert type(seconds)is int and seconds>0
        targets={2:600,3:480,4:300,5:90,6:60};expected={i for i,limit in targets.items()if seconds<=limit}
        assert 2 in expected and completed(rows[2])==expected
        notice(timed,start,expected,rows[2]);assert any(e.kind==0xc1 for e in timed.received[start:])
        before=rows
        await success(timed,0xad,last);await success(timed,0xbb,bytes(1));await timed.query(0x6be);await timed.query(0x6be)
        assert snapshot()==before
        report.update(ok=True,completed=[sorted(completed(r))for r in rows],timed_seconds=seconds,stages=stages,
            checks=['Actual official7D4/342/349/both34A/91/96/A7/AA/both9E settles one match; immediate distinct13/16 notices; loading/death alone add none',
                'Repeated9E/6BE are stable; missing original group3000010 refuses2005 and remains unreceived; normal67/225/227 returns; alternative character shares completion and independent display',
                'Actual41400 mode2/37F admission and nativeB2 roster deaths/BB/B3 traverse four unique rooms on unpatched server clock; only committedC1 records time and immediately completes eligible original thresholds',
                'Repeated terminalAD/BB/6BE add no clear record or completion; PvP accounts gain no timed credit; timed account gains no PvP credit'],
            native_Game=False,natural_GUI=False,natural_acquisition=False,natural_battle=False,production_clock_patch=False,
            explicit_readiness_and_combat_reports=True)
    finally:
        for p in reversed(peers):await p.close()
        for writer,tasks in relays:
            for task in tasks:task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True);writer.close()
            try:await writer.wait_closed()
            except ConnectionError:pass
