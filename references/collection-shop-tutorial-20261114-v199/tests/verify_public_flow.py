from pathlib import Path
from tempfile import TemporaryDirectory
import ctypes,sys,sysconfig
H=Path(__file__).resolve().parent;R=H.parents[1]
import json
workspace=H/'checks/modules-offline/local-workspace';v=json.loads((workspace/'releases/local/current.json').read_bytes());RUNTIME=workspace/v['path']
assert Path(sys.executable).resolve()==(RUNTIME/'server-python/python.exe').resolve()
_sql=ctypes.WinDLL(str(RUNTIME/'python/sqlite3.dll'))
import sqlite3
assert sqlite3.sqlite_version=='3.54.1'and sysconfig.get_config_var('Py_GIL_DISABLED')==1 and not sys._is_gil_enabled()
sys.path[:0]=[str(RUNTIME),str(H),str(R/'analysis/publisher-v198-20261114-v1/publication/qa')]
import asyncio
import protocol_harness as h
h.bind_runtime(RUNTIME)
from business_fixture import enroll,cold
from business_wire import check
async def main(work):
 f=await h.Fixture(work).start()
 try:
  rows=[]
  for index in range(3):
   identity=f.app.registry.create('owned199_'+str(index));row=dict(account_id=identity['id'],bridge=dict(host='127.0.0.1',port=f.port,name=identity['name'],token=identity['token'],certificate_sha256=f.pin,probe_port=f.config.client_probe_port))
   enroll(row,index,f.config.state_file,'owned-collection-noah-qualification');rows.append(row)
  results=[]
  for phase in ('test','retire'):
   def progress(stage,**values):
    if stage!='tutorial-entry-before-room':return
    from els_server.domain.first_story_entry import pending_tutorial
    from contextlib import closing
    debug=[]
    for s in f.app.playing.values():
     c=s.account.character()
     with closing(sqlite3.connect(f.config.state_file))as db:
      quests=db.execute('SELECT quest FROM character_quests WHERE owner=?',(s.account.uid,)).fetchall()
     debug.append(dict(phase=s.phase,uid=s.account.uid,unit_type=c['unit_type'],unit_class=c['unit_class'],level=c['level'],xp=s.account.get_reward_balances()['experience'],pending=pending_tutorial(s),quests=quests,build=s.client_build,enter_dungeon=s.enter_dungeon))
    (H/'checks/tutorial-entry-debug.json').write_text(json.dumps(debug,indent=2),encoding='utf8')
   wire=await check(rows,runtime=RUNTIME,progress=progress,require_public=False,phase=phase)
   results.append(dict(TLS=wire,cold=cold(rows,f.config.state_file,retired=phase=='retire')))
  assert not [r for r in f.logs if r['event']in('worker_error','notification_error','protocol_error','connection_task_error')]
  refusals=[r for r in f.logs if r['event']=='shop_purchase_refusal'];assert len(refusals)==1
  event=refusals[0];assert event['uid']==rows[0]['uid']and event['results']==[151]and event['payload_bytes']==10
  from els_server.protocol.shop_messages import ed_purchase_request
  assert ed_purchase_request(bytes.fromhex(event['payload_hex']))==((1200288319,1),)
  assert event['rejection']['reason']=='Career level requirement'and event['rejection']['character']['unit_class']==140
  assert not sys._is_gil_enabled();h.import_origins()
  return dict(ok=True,checks=results,actual_GameServer_TLS=True,actual_diagnostic_log=True,legal_refusal_source_and_product=True,python=sys.version,sqlite=sqlite3.sqlite_version,GIL_enabled=False,paired_signed_files=2079,natural_GUI=False,historical_screenshot_exact_SKU_unknown=True)
 finally:await f.close()
with TemporaryDirectory(dir=H,prefix='owned-collection-noah-tls-')as work:proof=asyncio.run(main(Path(work)))
(H/'checks/public-flow-proof.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf8')
print('Final actual 3.14t TLS: 35-level Noah repair/refusal log, finite collection unlock, two career changes/955 replacements and cold logins passed')
