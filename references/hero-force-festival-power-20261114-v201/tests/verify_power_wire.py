"""Qualify only the new CP public-wire helper on the combined private runtime."""
from pathlib import Path
import asyncio,ctypes,json,sys,time,uuid
H=Path(__file__).resolve().parent;R=H/'runtime/combined';W=H/'checks/power-wire-v2';W.mkdir(parents=True)
sys.path[:0]=[str(H),str(H.parent/'publisher-latency-20261114-v200/publication/qa'),str(R),str(R/'tools')]
engine=ctypes.WinDLL(str(R/'python/sqlite3.dll'))
import sqlite3
assert sqlite3.sqlite_version=='3.54.1'and not sys._is_gil_enabled()
import protocol_harness as harness
harness.bind_runtime(R)
from els_server.friends_bridge import Bridge,BridgeConfig
import power_fixture as fixture,power_wire as wire

async def main():
    test=harness.Fixture(W);results=[];peer=None
    try:
        await test.start();identity=await test.app.call(test.app.registry.create,'qa200power'+uuid.uuid4().hex[:8])
        row=dict(account_id=identity['id'],bridge=dict(host='127.0.0.1',port=test.port,name=identity['name'],token=identity['token'],certificate_sha256=test.pin,probe_port=test.config.client_probe_port))
        await test.app.call(fixture.enroll,row,3,test.config.state_file,'owned-power-wire-'+uuid.uuid4().hex)
        for phase in ('test','retire'):
            peer=await harness.Peer.open(Bridge(BridgeConfig(**row['bridge'])));await harness.enter(peer,row['uid'])
            results.append(await wire.check(row,peer,phase=phase));await peer.close();peer=None
            deadline=time.monotonic()+15
            while test.server.connections and time.monotonic()<deadline:await asyncio.sleep(.02)
            assert not test.server.connections
            results.append(fixture.cold(row,test.config.state_file,retired=phase=='retire'))
        assert not[event for event in test.logs if event['event']in('worker_error','notification_error','connection_task_error','protocol_error')]
        proof=dict(ok=True,results=results,source_bindings=json.loads((H/'server-input-binding.json').read_bytes())['server_files'],GIL_enabled=False,public_network=False,native_session=False)
        (W/'result.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        print('Actual TLS CP reports, Lu/Ciel raw bands, ERP crossing, AD replay and cold facts passed')
    finally:
        if peer:await peer.close()
        await test.close()
        (W/'events-private.json').write_text(json.dumps(test.logs,ensure_ascii=False,indent=2,default=str),encoding='utf8')

if __name__=='__main__':asyncio.run(main())
