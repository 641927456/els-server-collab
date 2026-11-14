from pathlib import Path
import asyncio,ctypes,json,sys,time,uuid
H=Path(__file__).resolve().parent;R=H/'runtime/combined';W=H/'checks/flow';W.mkdir(parents=True)
sys.path[:0]=[str(H),str(H.parent/'publisher-v201-20261114-v1/publication/qa'),str(R),str(R/'tools')]
engine=ctypes.WinDLL(str(R/'python/sqlite3.dll'))
import sqlite3
assert sqlite3.sqlite_version=='3.54.1'and not sys._is_gil_enabled()
import protocol_harness as harness
harness.bind_runtime(R)
import business_fixture as fixture,business_wire as wire

async def main():
    test=harness.Fixture(W);rows=[];phases=[]
    try:
        await test.start()
        for index in range(1):
            identity=await test.app.call(test.app.registry.create,'qa205roster'+uuid.uuid4().hex[:8])
            row=dict(account_id=identity['id'],bridge=dict(host='127.0.0.1',port=test.port,name=identity['name'],token=identity['token'],certificate_sha256=test.pin,probe_port=test.config.client_probe_port))
            await test.app.call(fixture.enroll,row,index,test.config.state_file,'owned-reads-'+uuid.uuid4().hex);rows.append(row)
        for phase in('test','retire'):
            phases.append(await wire.check(rows,runtime=R,progress=lambda *a,**kw:None,require_public=False,phase=phase))
            deadline=time.monotonic()+15
            while test.server.connections and time.monotonic()<deadline:await asyncio.sleep(.02)
            assert not test.server.connections
            phases.append(fixture.cold(rows,test.config.state_file,retired=phase=='retire'))
        assert not[event for event in test.logs if event['event']in('worker_error','notification_error','connection_task_error','protocol_error')]
        (W/'result.json').write_text(json.dumps(dict(ok=True,actual_TLS=True,public_network=False,phases=phases,GIL_enabled=False),indent=2)+'\n',encoding='utf8')
        print('V205 combined TLS status/resume, Lu/Ciel CP/Greed replay and cold checks passed')
    finally:await test.close()

if __name__=='__main__':asyncio.run(main())
