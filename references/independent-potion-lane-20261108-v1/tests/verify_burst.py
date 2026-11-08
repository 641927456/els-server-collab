"""Real TLS burst of death requests followed by one authoritative potion use."""
import asyncio,contextlib,json,struct,time
import runtime_fixture as h
import sqlite3
from profile_death import seed,death
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage.quick_slots import save_request,empty
from els_server.domain.quick_bindings import item_binding
from els_server.storage.resonance_state import snapshot

async def main():
    c=h.f.FriendsTests();await c.asyncSetUp();result=dict(ok=False,owned_fixture=True)
    try:
        uid=seed(c)
        with contextlib.closing(sqlite3.connect(c.config.state_file)) as db,db:
            grant_items(db,[dict(template=130165,metadata=2,group=6,quantity=10)],uid)
        slots=empty();slots[0]=item_binding(130165)
        save_request(c.config.state_file,struct.pack('>iI',1,len(slots))+b''.join(struct.pack('>ii',k,v)for k,v in slots.items()),uid)
        peer=await c.peer(c.alice);await peer.roster();await peer.enter_town(uid)
        async with asyncio.timeout(8):
            while not any(e.get('event')=='request_timing'and e.get('kind')==0x227 for e in c.events):await asyncio.sleep(.001)
        s=c.app.playing[c.alice['id']];run=h.room(s)
        npcs=[n for n in run.current['npcs'] if n['active'] and not n['no_drop'] and not n.get('ally')]
        chosen=npcs[:min(6,len(npcs)-1)];assert len(chosen)>=3
        peer.observed.clear();sent=[]
        for npc in chosen:
            request=death(npc,uid);await peer.send(request.kind,request.payload);sent.append(request)
        started=time.perf_counter()
        await peer.send(0x113,struct.pack('>HBBB',0,0,0,0))
        ack=await peer.until(0x114);elapsed=(time.perf_counter()-started)*1000
        assert struct.unpack_from('>i',ack.payload)[0]==0
        effect=await peer.until(0x115);assert struct.unpack_from('>Qi',effect.payload)==(uid,130165)
        completed_at_potion=len(run.defeated)
        async with asyncio.timeout(8):
            while len(run.defeated)<len(chosen):await asyncio.sleep(.01)
        with contextlib.closing(sqlite3.connect(c.config.state_file)) as db:
            state=snapshot(db,uid,c.alice['id']);xp=state['experience']
            count=sum(i['count']for i in load_items(db,uid)if i['template']==130165)
            kills=db.execute('SELECT COUNT(*) FROM pve_kill_experience WHERE owner=? AND run_id=?',(uid,run.run_id)).fetchone()[0]
            uses=db.execute('SELECT COUNT(*) FROM consumable_uses WHERE owner=?',(uid,)).fetchone()[0]
        assert xp>0 and count==9 and kills==len(chosen)and uses==1
        observed=list(peer.observed)
        # A duplicate death reuses its receipt. A second immediate potion is
        # rejected by the real cooldown; neither operation increments saves.
        await peer.send(sent[0].kind,sent[0].payload);await peer.until(0xae)
        await peer.send(0x113,struct.pack('>HBBB',0,0,0,0))
        rejected=await peer.until(0x114);assert struct.unpack_from('>i',rejected.payload)[0]==1369
        with contextlib.closing(sqlite3.connect(c.config.state_file)) as db:
            assert snapshot(db,uid,c.alice['id'])['experience']==xp
            assert sum(i['count']for i in load_items(db,uid)if i['template']==130165)==9
            assert db.execute('SELECT COUNT(*) FROM pve_kill_experience WHERE owner=? AND run_id=?',(uid,run.run_id)).fetchone()[0]==kills
            assert db.execute('SELECT COUNT(*) FROM consumable_uses WHERE owner=?',(uid,)).fetchone()[0]==1
        timings=[r for r in c.events if r['event']=='request_timing'and r.get('kind')in(0xad,0x113)]
        result.update(ok=True,deaths=len(chosen),potion_latency_ms=elapsed,potion_count=count,
            completed_deaths_at_potion=completed_at_potion,
            xp=xp,unique_kill_receipts=kills,unique_potion_receipts=uses,
            duplicate_death_no_award=True,cooldown_refusal_no_debit=True,
            D9_count=sum(e['received']==0xd9 for e in observed),
            ERP610_count=sum(e['received']==0x610 for e in observed),
            timings=[{k:r[k]for k in('kind','sequence','total_ms','connection_wait_ms')if k in r}for r in timings])
        candidate='--candidate'in h.sys.argv
        if candidate:
            assert result['D9_count']==0 and result['ERP610_count']>=1
            potion_timings=[r for r in c.events if r['event']=='request_timing'and r.get('kind')==0x113]
            assert potion_timings[0].get('calls')==[{'lane':'consumable'}],potion_timings[0]
            assert completed_at_potion<len(chosen),completed_at_potion
    finally:
        await c.asyncTearDown();result['cleaned']=not c.root.exists()
        name='candidate'if'--candidate'in h.sys.argv else'baseline'
        (h.H/('burst-'+name+'.json')).write_text(json.dumps(result,indent=2)+'\n','utf8')
    print(json.dumps(result))

if __name__=='__main__':asyncio.run(main())
