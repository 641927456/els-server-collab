"""Current pinned ONLINE code, own TLS and DBs, existing native reader helpers."""
import bootstrap
import importlib.util,os,sqlite3,struct,sys,time,uuid
from pathlib import Path
from dataclasses import replace
H=bootstrap.HERE;ROOT=bootstrap.ROOT;BASE=bootstrap.BASE
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
f=load('dungeon_tls_fixture',ROOT/'tests/test_friends_server.py')
from els_server.config import ServerConfig
f.ServerConfig=lambda **kw:replace(ServerConfig(**kw),attribute_enchant_enabled=True,normal_equipment_moves_enabled=True,equipment_repair_enabled=True)
from els_server.protocol.protocol_codec import Event,encode_event,encode_frame
async def send(self,kind,payload=b'',event_id=0x202):
 if kind==0x5bf and not payload:payload=bytes(8)
 self.writer.write(encode_frame(encode_event(Event(event_id,kind=kind,payload=payload,performers=(0,))),self.keys,spi=self.spi,sequence=self.outgoing));self.outgoing+=1;await self.writer.drain()
f.Peer.send=send
_teardown=f.FriendsTests.asyncTearDown
_setup=f.FriendsTests.asyncSetUp
async def setup(self):
 try:
  await _setup(self)
  if bootstrap.FREE_THREADED_BUILD:assert not sys._is_gil_enabled(),'A native dependency re-enabled the GIL during startup'
 except BaseException:
  try:
   if hasattr(self,'server'):await self.server.close()
  finally:
   try:
    if hasattr(self,'app'):self.app.close()
   finally:
    if hasattr(self,'tmp'):self.tmp.cleanup()
  raise
f.FriendsTests.asyncSetUp=setup
async def teardown(self):
 errors=[r for r in self.events if r['event']in('worker_error','notification_error','connection_task_error')]
 if errors:
  import json
  target=H/('owned-error-details-'+time.strftime('%H%M%S')+'.json')
  target.write_text(json.dumps(errors,indent=2),'utf8')
  print('Owned errors: '+json.dumps(errors),flush=True)
 await _teardown(self)
 if bootstrap.FREE_THREADED_BUILD:assert not sys._is_gil_enabled(),'A native dependency re-enabled the GIL during gameplay'
 import hashlib,json
 evidence=H/'runtime-evidence';evidence.mkdir(exist_ok=True)
 script=Path(sys.modules['__main__'].__file__)
 label=script.stem+'-py'+str(sys.version_info.major)+str(sys.version_info.minor)+('t'if bootstrap.FREE_THREADED_BUILD else'')
 (evidence/(label+'.json')).write_text(json.dumps(dict(runtime=sys.version,executable=sys.executable,GIL_enabled=sys._is_gil_enabled(),script_sha256=hashlib.sha256(script.read_bytes()).hexdigest(),candidate_bindings=bootstrap.SOURCE_BINDINGS,owned_runtime_removed=not self.root.exists(),connections=len(self.server.connections)),indent=2),'utf8')
f.FriendsTests.asyncTearDown=teardown
load('dungeon_continuous_reader',ROOT/'analysis/server-economy-workers-20261102-v1/native_fixture_reader.py').install(f)
# Reuse only owned drop/room builders, without their old release/module overlays.
import ast
source=ast.parse((ROOT/'analysis/pickup-consumable-gate-20261104-v1/runtime_fixture.py').read_bytes())
for node in source.body:
 if isinstance(node,ast.FunctionDef)and node.name in('room','drop'):
  if node.name=='room':
   for child in ast.walk(node):
    if isinstance(child,ast.Constant)and child.value==34710:child.value=34720
  exec(compile(ast.Module(body=[node],type_ignores=[]),'owned-dungeon-helper','exec'),globals())
