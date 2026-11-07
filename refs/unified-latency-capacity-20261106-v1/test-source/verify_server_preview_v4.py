"""Actual packaged interpreter and full source tree; original native fixture inputs."""
from pathlib import Path
import ast,asyncio,contextlib,hashlib,importlib.util,json,os,sqlite3,sys,tempfile,types
from dataclasses import replace
H=Path(__file__).resolve().parent;root=H/'server-preview-v4';assert Path(sys.executable).resolve()==root/'server-python/python.exe'
tempfile.tempdir=str(H)
from els_server.application import Application
assert root in Path(Application.__init__.__code__.co_filename).resolve().parents
assert not sys._is_gil_enabled()
source=Path('G:/els/tests/test_friends_server.py');text=source.read_text('utf8');assert text.count('sys.path.insert(0,str(ROOT))')==1
fixture=types.ModuleType('packaged_native_fixture');fixture.__file__=str(source);sys.modules[fixture.__name__]=fixture
exec(compile(text.replace('sys.path.insert(0,str(ROOT))','None'),str(source),'exec'),vars(fixture))
from els_server.config import ServerConfig
fixture.ServerConfig=lambda **kw:replace(ServerConfig(**kw),attribute_enchant_enabled=True,normal_equipment_moves_enabled=True,equipment_repair_enabled=True)
from els_server.protocol.protocol_codec import Event,encode_event,encode_frame
tree=ast.parse((H/'runtime_fixture.py').read_bytes());node=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef)and n.name=='send')
scope=dict(Event=Event,encode_event=encode_event,encode_frame=encode_frame);exec(compile(ast.Module(body=[node],type_ignores=[]),'existing-native-send','exec'),scope);fixture.Peer.send=scope['send']
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
load('packaged_continuous_reader',Path('G:/els/analysis/server-economy-workers-20261102-v1/native_fixture_reader.py')).install(fixture)
from els_server.storage.characters import Characters
from els_server.storage.seal_quests import QuestState
from els_server.storage.inventory_state import load_items,grant_items
from els_server.domain.inventory_items import TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS
from els_server.game_data import client_data
tree=ast.parse((H/'profile_town.py').read_bytes());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='seed')
exec(compile(ast.Module(body=[node],type_ignores=[]),'existing-owned-seed','exec'),globals())
probe=load('packaged_gate',Path('G:/els/analysis/glass-door-20261104-v1/repair-v3/gate_probe.py'))
async def main():
 c=fixture.FriendsTests();await c.asyncSetUp()
 try:
  uid=seed(c,c.alice,'PackagedOwn');p=await c.peer(c.alice);await p.roster();await c.server.periodics.close()
  await probe.solo_load(p,uid);s=c.app.playing[c.alice['id']]
  await probe.clear_first(p,uid,s.dungeon_run);await probe.finish_solo(p)
  assert not any(r['event']in('worker_error','notification_error','connection_task_error')for r in c.events)
  assert not sys._is_gil_enabled()
 finally:await c.asyncTearDown()
 for name in('els_server.application','els_server.game_data','els_server.protocol.dungeon_messages','els_server.storage.death_writer'):
  assert root in Path(sys.modules[name].__file__).resolve().parents,name
 out=dict(passed=True,actual_packaged_interpreter=str(sys.executable),actual_full_source_tree=str(root),GIL_enabled=sys._is_gil_enabled(),native_town_and_dungeon_admission=True,actual_deaths_and_glass_transition=True,own_runtime_removed=not c.root.exists(),production_installed=False)
 (H/'server-preview-v4-tests.json').write_text(json.dumps(out,indent=2),'utf8');print(json.dumps(out))
from els_server.__main__ import _native_timing
with _native_timing():asyncio.run(main())
