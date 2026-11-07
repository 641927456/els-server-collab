"""One new ordinary-route qualification on the actual assembly-selected runtime."""
from pathlib import Path
import asyncio,hashlib,importlib.util,json,os,sys,traceback
D=Path(__file__).resolve().parent;H=D.parent;W=H.parent;R=Path('G:/els')
read=lambda p:json.loads(Path(p).read_bytes())
selected=Path(read(D/'launcher-preview-v103/built-selection-verification.json')['selected_root'])
os.environ['ELS_CRASH_TEST_RUNTIME']=str(selected);sys.argv=[__file__];sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('owned_selected_ship_fixture',W/'reproduce_tutorial_late_death.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
sys.path.insert(0,str(D));import repair_client as c,repair_fixture
from protocol_client import Peer

async def main():
 f=r.f.FriendsTests();await f.asyncSetUp();report={'ok':False}
 try:
  uid=r.f.Characters(f.config.state_file,f.alice['id']).create('ShipRoute',1,'ship-route')['uid']
  values=[dict(account_id=f.alice['id'],uid=uid,unit_type=1)];repair_fixture.seed(f.config.state_file,values)
  async def connect(value,peers):
   peer=await f.peer(f.alice);await peer.roster();await peer.enter_town(uid)
   peer.received=[];put=peer.pending.put_nowait
   def record(event):peer.received.append(event);put(event)
   peer.pending.put_nowait=record;peer.query=Peer.query.__get__(peer);peers.append(peer);return peer
  c.connect=connect
  try:await c.scenario(values,lambda:repair_fixture.snapshot(f.config.state_file,values),report)
  except BaseException:
   details=f.events[-25:]
   (D/'selected-route-failure.private.json').write_text(json.dumps(details,indent=2)+'\n','utf8');raise
  assert not any(e['event']in('worker_error','notification_error','protocol_error')for e in f.events)
  for row in read(D/'candidate-manifest.json')['files']:
   assert hashlib.sha256((selected/row['path']).read_bytes()).hexdigest()==row['sha256']
  import els_server.transport
  assert Path(els_server.transport.__file__).resolve()==(selected/'els_server/transport.py').resolve()
  report.update(actual_selected_runtime=str(selected),actual_selected_Application=True,explicit_scene_mutation=False,production_modified=False)
  return report
 finally:await f.asyncTearDown()

if __name__=='__main__':
 result={'ok':False}
 try:
  result=asyncio.run(main());b=read(D/'launcher-preview-v103/build.json')
  (D/'built-runtime-qualification.json').write_text(json.dumps(dict(result,exe_sha256=b['exe_sha256']),indent=2)+'\n','utf8')
 except BaseException:result={'ok':False,'error':traceback.format_exc()};raise
 finally:(D/'qa-scenario-qualification.json').write_text(json.dumps(result,indent=2)+'\n','utf8');print(json.dumps(result))
