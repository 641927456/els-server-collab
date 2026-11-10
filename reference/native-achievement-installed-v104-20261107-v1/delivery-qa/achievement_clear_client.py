"""Normal34350 admission and final receipt using only delivered NPC identities."""
import asyncio,struct
from achievement_protocol_client import connect
from els_server.domain.dungeon_npcs import MODE0_FIELDS
from els_server.domain.achievement_catalog import points
from els_server.protocol import achievement_messages as wire
ENTRY=bytes.fromhex('eefc726aad751f003e6b6d2e0c4d36e2923600000010332b6d21282a5c1774790f0f3a4c7947')

def population(event):
    raw=event.payload;stage=struct.unpack_from('>i',raw)[0];offset=8
    parts=struct.unpack_from('>I',raw,offset)[0];offset+=4;rows=[]
    assert parts==1
    part,opaque,count=struct.unpack_from('>iII',raw,offset);offset+=12
    assert part==opaque==0 and count>0
    for _ in range(count):
        fields={}
        for off,size,key,kind in MODE0_FIELDS:
            assert offset+size<=len(raw)
            value=int.from_bytes(raw[offset:offset+size],'big');offset+=size
            if kind=='empty':assert value==0
            else:fields[off]=value^key
        rows.append(dict(key=fields[0],template=fields[4],active=bool(fields[0x4e])))
    assert len({n['key']for n in rows})==len(rows)
    return stage,part,rows

def death(npc,owner):
    # Existing solo prototype accepts an authenticated positive scalar.
    # One is an explicit report fixture, never a native maximum-HP claim.
    return(struct.pack('>iBQQ6fBf',npc['key'],0,owner,owner,0.,0.,0.,0.,0.,0.,0,1.)
        +bytes(8)+struct.pack('>Q',0)+bytes(4)+struct.pack('>Q',owner))

async def scenario(values,snapshot,report):
    peers=[]
    async def current():return await asyncio.to_thread(snapshot)
    async def success(p,kind,body=b'',reply=None):
        answer=await p.query(kind,body,reply);assert answer.payload[:4]==bytes(4),(hex(kind),answer.payload[:20].hex())
        return answer
    try:
        value=values[2];before=await current()
        assert [r['clear_count']for r in before]==[0,0,99]
        uid=value['clear_uid'];identity=dict(value,uid=uid,character_name=value['clear_name'],town=20001)
        p=await connect(identity,peers)
        assert 373 not in {r['id']for r in(await current())[2]['clear_achievement']['completed']}
        admitted=await success(p,0x7d4,struct.pack('>ii',1,34350))
        mode=struct.unpack_from('>i',admitted.payload,4)[0]
        await success(p,0x37f if mode==2 else 0x382,ENTRY)
        await success(p,0x91,struct.pack('>ii',100,0));await success(p,0xb3,bytes(9))
        assert(await current())[2]['clear_count']==99
        await asyncio.sleep(1.1);stages=[];last=None;start=None
        for step in range(2):
            event=next(e for e in reversed(p.received)if e.kind==0xb2)
            stage,part,npcs=population(event);stages.append(stage);arrival=len(p.received)
            for npc in npcs:
                if any(e.kind==0xba for e in p.received[arrival:]):break
                if npc['active']:last=death(npc,uid);await success(p,0xad,last)
            assert any(e.kind==0xba and e.payload==struct.pack('>b',part)for e in p.received[arrival:])
            if step==0:assert(await current())[2]['clear_count']==99
            start=len(p.received);await success(p,0xbb,struct.pack('>b',part))
            if step==0:await success(p,0xb3,bytes(9))
        assert stages==[0,1]
        after=await current();row=after[2]
        assert [r['clear_count']for r in after]==[0,0,100]and after[:2]==before[:2]
        status=row['clear_achievement'];fresh=[r for r in status['completed']if r['id']==373];assert len(fresh)==1
        notice=wire.completion(fresh,points(status['completed']),status['watched'],False).payload
        assert any(e.kind==0xc1 for e in p.received[start:])
        assert any(e.kind==0x6c0 and e.payload==notice for e in p.received[start:])
        await success(p,0xad,last);await success(p,0xbb,bytes(1))
        for _ in range(2):await p.query(0x6be)
        assert await current()==after
        await p.close();peers.remove(p)
        p=await connect(dict(value,town=1500),peers);await p.query(0x6be)
        cold=await current();assert cold[2]['clear_count']==100
        assert 373 in {r['id']for r in cold[2]['achievement']['completed']}
        assert cold[2]['achievement']['watched']==[]
        report.update(ok=True,checks=[*report.get('checks',[]),
            '34350 normal prerequisite admission and nativeB2 identities traverse two rooms; loading and first room retain99, final committedC1 reaches100 and emits373 immediately',
            'TerminalAD/BB/6BE replay remains stable; cold sibling shares373; other accounts retain zero clears'],
            actual_protocol_final_clears=1,clear_history_fixture_receipts=99,clear_prerequisite_quest_fixture=26650,
            clear_stages=stages,native_spawn_roster=True,explicit_positive_death_report_fixture=True,
            natural_battle=False,native_Game=False,natural_GUI=False)
    finally:
        for p in reversed(peers):await p.close()
