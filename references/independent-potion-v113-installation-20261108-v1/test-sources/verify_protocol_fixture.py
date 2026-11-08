"""Validate the actual-public request fixture on the selected isolated server."""
from pathlib import Path
import asyncio,ctypes,hashlib,json,os,sys,sysconfig,tempfile,types
W=Path(__file__).resolve().parent;R=Path('G:/els');read=lambda p:json.loads(Path(p).read_bytes())
D=Path(read(W/'delivery-plan.json')['build_path']).parent;B=Path(read(D/'built-selection-verification.json')['selected_root'])
output=W/'publication/protocol-fixture-v3';assert not output.exists();output.mkdir()
stub=types.ModuleType('bootstrap');stub.HERE=output;stub.ROOT=R;stub.BASE=B
stub.SOURCE_BINDINGS={r['path']:r['sha256']for r in read(W.parent/'candidate.json')['files']};stub.FREE_THREADED_BUILD=sysconfig.get_config_var('Py_GIL_DISABLED')==1
assert stub.FREE_THREADED_BUILD and not sys._is_gil_enabled()
assert 'sqlite3'not in sys.modules
sqlite_runtime=ctypes.WinDLL(str(B/'python/sqlite3.dll'))
import sqlite3
sys.modules['bootstrap']=stub;sys.dont_write_bytecode=True
os.environ.update(TEMP=str(output),TMP=str(output));tempfile.tempdir=str(output)
sys.path[:0]=[str(B),str(W.parent),str(R/'analysis/server-latency-20261106-v7'),str(R),str(R/'tools'),str(R/'tools/pylibs'),str(R/'tools/launcher_testdeps'),str(R/'analysis/town-dungeon-latency-20261105-v6/free-thread-deps')]
import els_server.application,els_server.transport,els_server.friends_bridge
import runtime_fixture as h
from els_server.storage.characters import Characters
from els_server.storage.inventory_state import grant_items
from els_server.storage.quick_slots import save_request,empty
from els_server.domain.quick_bindings import item_binding
from contextlib import closing
import struct
sys.path.insert(0,str(W))

async def main():
 c=h.f.FriendsTests();await c.asyncSetUp()
 try:
  from protocol_potion_qa import qualify
  uid=Characters(c.config.state_file,c.alice['id']).create('OwnPubPotion',1,'own-public-fixture',quick_start=True)['uid']
  from repair_fixture import seed_role_experience
  seed_role_experience(c.config.state_file,uid,c.alice['id'],'own-public-fixture')
  with closing(sqlite3.connect(c.config.state_file))as db,db:grant_items(db,[dict(template=130165,metadata=2,group=6,quantity=10)],uid)
  slots=empty();slots[0]=item_binding(130165)
  save_request(c.config.state_file,struct.pack('>iI',1,len(slots))+b''.join(struct.pack('>ii',k,v)for k,v in slots.items()),uid)
  value=dict(uid=uid,bridge=dict(host='127.0.0.1',port=c.port,name=c.alice['name'],token=c.alice['token'],certificate_sha256=c.pin))
  result=await qualify(value)
  with closing(sqlite3.connect(c.config.state_file))as db:
   assert db.execute('SELECT SUM(count)FROM inventory_items WHERE owner=?AND template=130165',(uid,)).fetchone()[0]==9
   assert db.execute('SELECT COUNT(*)FROM consumable_uses WHERE owner=?',(uid,)).fetchone()[0]==1
  timings=[r for r in c.events if r.get('event')=='request_timing'and r.get('kind')==0x113]
  assert len(timings)==2 and all(r['calls']==[{'lane':'consumable'}]for r in timings),timings
  result.update(actual_selected_runtime=str(B),temporary_owned_database=True,independent_lane_verified=True,cold_count=9,unique_receipt=1)
 finally:await c.asyncTearDown()
 result['fixture_removed']=not c.root.exists();assert result['fixture_removed']
 (W/'actual-protocol-fixture.json').write_bytes((json.dumps(result,indent=2)+'\n').encode());print(json.dumps(result))
asyncio.run(main())
