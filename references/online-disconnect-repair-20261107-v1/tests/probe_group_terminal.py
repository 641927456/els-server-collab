"""Two owned authenticated peers: group clear, delayed AD/BB and no duplicate award."""
from pathlib import Path
import asyncio,importlib.util,json,sqlite3,struct,sys,traceback
from contextlib import closing
W=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('owned_group_setup',W/'reproduce_tutorial_late_death.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
from els_server.domain.dungeon_population import population

def economic_rows(path):
    with closing(sqlite3.connect(path))as db:
        db.execute('BEGIN')
        return {name:db.execute('SELECT *FROM '+name+' ORDER BY rowid').fetchall()
                for name in ['reward_balances','reward_receipts']}

async def run():
    f=r.f.FriendsTests();await f.asyncSetUp()
    try:
        a,b,auid,buid=await f.coop_pair();await f.coop_start(a,b)
        members=list(f.app.playing.values())
        assert len(members)==2 and all(getattr(m,'_c1_hp_context',None)is None for m in members)
        last=None
        for stage in range(3):
            await f.coop_load(a,b)
            current=population(stage)
            order=[n for n in current['npcs']if n['active']and n['key']!=current['clear_key']]+[next(n for n in current['npcs']if n['key']==current['clear_key'])]
            for npc in order:
                last=(struct.pack('>iBQQ6fBf',npc['key'],0,auid,buid,0.,0.,0.,1.,2.,3.,0,npc['hp'])
                    +struct.pack('>IQf',1,buid,1.)+struct.pack('>IQB',1,buid,1)+bytes(8)+bytes(4)+struct.pack('>Q',buid))
                await a.send(0xad,last);assert(await a.until(0xae)).payload==bytes(4);await b.until(0xaf)
            assert all(m.part_end_notified for m in members)
            await a.send(0xbb,b'\0');await a.until(0xbc)
            await b.send(0xbb,b'\0');await b.until(0xbc)
            if stage<2:await asyncio.gather(a.until(0xb2),b.until(0xb2))
            else:await asyncio.gather(a.until(0xc1),b.until(0xc1))
        assert all(m.clear_notified for m in members)
        before=economic_rows(f.config.state_file)
        for peer in [a,b]:
            for kind,raw in [(0xad,last),(0xbb,b'\0'),(0xb3,bytes(9))]:
                await peer.send(kind,raw);await peer.send(0x48d);await peer.until(0x48f)
        assert economic_rows(f.config.state_file)==before
        assert not any(e['event']in ('protocol_error','worker_error')for e in f.events)
        return dict(ok=True,owned_members=2,actual_Application=True,actual_TLS=True,
            normal_three_stage_group_clear=True,shared_room_has_no_solo_HP_context=True,
            late_AD_BB_B3_connection_kept=True,reward_rows_unchanged=True,
            production_modified=False,natural_GUI=False,natural_combat=False)
    finally:await f.asyncTearDown()

if __name__=='__main__':
    result={}
    try:result=asyncio.run(run())
    except BaseException:result=dict(ok=False,error=traceback.format_exc());raise
    finally:
        (W/'variants-v1/group-terminal.json').write_text(json.dumps(result,indent=2)+'\n','utf8')
        print(json.dumps(result))
