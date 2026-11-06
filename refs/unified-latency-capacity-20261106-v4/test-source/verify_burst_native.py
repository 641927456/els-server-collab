import runtime_fixture as h
import asyncio,json,sqlite3,sys,time
from contextlib import closing
from dataclasses import asdict
from profile_town import seed

async def main():
    c=h.f.FriendsTests();await c.asyncSetUp();process=None
    W=h.H/'local-town-burst-native-v1';assert not W.exists();W.mkdir()
    def save(name,value):(W/name).write_text(json.dumps(value),'utf8')
    async def wait(name):
        async with asyncio.timeout(100):
            while not(W/name).exists():
                assert process.returncode is None,'Native burst client ended before '+name
                await asyncio.sleep(.02)
    try:
        identities=[c.alice,c.bob];uids=[seed(c,v,'OwnBurst'+str(i),False)for i,v in enumerate(identities)]
        save('credentials.private.json',[dict(uid=uid,bridge=asdict(c.bridge(identity).config))for uid,identity in zip(uids,identities)])
        save('admission-start.json',dict(monotonic=time.perf_counter()+1))
        from importlib.util import spec_from_file_location,module_from_spec
        spec=spec_from_file_location('own_gm_probe',h.H/'isolated-online/harness/gm_read_probe.py');module=module_from_spec(spec);spec.loader.exec_module(module)
        probe=module.GMReadProbe(c.app,c.server,c.root/'gm-unused.sqlite3')
        stream=(W/'client.private.log').open('xb')
        process=await asyncio.create_subprocess_exec('C:/Users/Administrator/AppData/Local/Programs/Python/Python313/python.exe','-B','-X','utf8',str(h.H/'town_burst_capacity_client.py'),'--candidate','--run',W.name,'--worker','town','--offset','0','--count','2','--total','2','--seconds','60','--admission-interval','.75',cwd='G:/els',stdout=stream,stderr=asyncio.subprocess.STDOUT)
        await wait('town-ready.json');save('town-start.json',dict(monotonic=time.perf_counter()+1))
        await wait('town-moved.json');save('town-drain.json',dict(ok=True))
        async with asyncio.timeout(15):assert await process.wait()==0
        stream.close();row=json.loads((W/'town-result.json').read_bytes());assert row['ok']and row['counts']==dict(moves=700,relays=700)
        with closing(sqlite3.connect(c.config.state_file))as db:
            assert all(db.execute('SELECT town,x FROM location WHERE uid=?',(uid,)).fetchone()==(20000,349.)for uid in uids)
        hist=json.loads((W/'town-samples.private.json').read_bytes())
        assert hist['movement_relay_burst']['n']==200 and hist['movement_relay_steady']['n']==500
        gm=probe.snapshot();assert gm['rows']==2 and gm['status_ms']['n']>=50
        await probe.close()
        out=dict(passed=True,actual_Python313_native_client=True,normal_native_TLS_selection_town_movement=True,steady_and_burst_frames_all_received=True,counts=row['counts'],burst_relays=200,steady_relays=500,final_SQL_positions_exact=True,real_GM_tick_and_status=True)
    finally:
        if process is not None and process.returncode is None:process.terminate();await process.wait()
        if'probe'in locals()and not probe.task.done():await probe.close()
        await c.asyncTearDown()
    out.update(owned_runtime_removed=not c.root.exists(),connections=len(c.server.connections))
    (h.H/'burst-native-tests.json').write_text(json.dumps(out,indent=2),'utf8');print(json.dumps(out))
asyncio.run(main())
