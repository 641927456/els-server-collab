from pathlib import Path
import asyncio,ctypes,hashlib,json,os,sys,time,uuid
H=Path(__file__).resolve().parent;R=H/'runtime/combined';W=H/'checks/flow';W.mkdir(parents=True)
sys.path[:0]=[str(H),str(H.parent/'publisher-latency-20261114-v200/publication/qa'),str(R),str(R/'tools')]
_sqlite=ctypes.WinDLL(str(R/'python/sqlite3.dll'))
import sqlite3
assert sqlite3.sqlite_version=='3.54.1'and not sys._is_gil_enabled()
import protocol_harness as harness
harness.bind_runtime(R)
import business_fixture as fixture,business_wire as wire
def save(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
async def main():
 f=harness.Fixture(W);rows=[]
 try:
  await f.start()
  for i in range(4):
   identity=await f.app.call(f.app.registry.create,'qa200flow'+uuid.uuid4().hex[:8])
   row=dict(account_id=identity['id'],bridge=dict(host='127.0.0.1',port=f.port,name=identity['name'],token=identity['token'],certificate_sha256=f.pin,probe_port=f.config.client_probe_port))
   await f.app.call(fixture.enroll,row,i,f.config.state_file,'owned-v201-'+uuid.uuid4().hex);rows.append(row)
  save(W/'credentials-private.json',rows)
  phases=[]
  def progress(label,**data):print(label,flush=True)
  for phase in('test','retire'):
   phases.append(await wire.check(rows,runtime=R,progress=progress,require_public=False,phase=phase))
   deadline=time.monotonic()+15
   while f.server.connections and time.monotonic()<deadline:await asyncio.sleep(.02)
   assert not f.server.connections
   phases.append(fixture.cold(rows,f.config.state_file,retired=phase=='retire'))
  assert not[e for e in f.logs if e['event']in('worker_error','notification_error','connection_task_error','protocol_error')]
  save(W/'result.json',dict(ok=True,actual_TLS=True,public_network=False,phases=phases,GIL_enabled=sys._is_gil_enabled(),source_bindings={r['path']:r['sha256']for r in json.loads((H/'composition.json').read_bytes())['files']if r['scope']=='server'}))
 finally:
  await f.close()
  (W/'credentials-private.json').unlink(missing_ok=True)
  save(W/'cleanup.json',dict(owned_connections_closed=not f.server or not f.server.connections))
if __name__=='__main__':asyncio.run(main())
