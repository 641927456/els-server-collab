"""Run relevant TLS behavior from the launcher's actual selected source tree."""
from pathlib import Path
import ctypes,hashlib,json,os,runpy,shutil,sys,sysconfig,tempfile,types
W=Path(__file__).resolve().parent;R=Path('G:/els');read=lambda p:json.loads(Path(p).read_bytes())
D=Path(read(W/'delivery-plan.json')['build_path']).parent
selection=read(D/'built-selection-verification.json');assert selection['ok'];B=Path(selection['selected_root'])
files=read(D/'runtime-files.json')['files'];assert len(files)==read(D/'build.json')['payload_files']
for row in files:
 p=B/row['path'];assert p.stat().st_size==row['size']and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256']
output=W/'publication/selected-runtime-probe-v2';assert not output.exists();output.mkdir()
shutil.copyfile(W.parent/'fixture-shape.json',output/'fixture-shape.json')
stub=types.ModuleType('bootstrap');stub.HERE=output;stub.ROOT=R;stub.BASE=B
stub.SOURCE_BINDINGS={r['path']:r['sha256']for r in read(W.parent/'candidate.json')['files']}
stub.FREE_THREADED_BUILD=sysconfig.get_config_var('Py_GIL_DISABLED')==1
assert stub.FREE_THREADED_BUILD and not sys._is_gil_enabled()
assert 'sqlite3'not in sys.modules
sqlite_runtime=ctypes.WinDLL(str(B/'python/sqlite3.dll'))
import sqlite3
assert sqlite3.sqlite_version=='3.54.1'
sys.modules['bootstrap']=stub
sys.dont_write_bytecode=True
os.environ.update(TEMP=str(output),TMP=str(output),PYTHONDONTWRITEBYTECODE='1');tempfile.tempdir=str(output)
sys.path[:0]=[str(B),str(W.parent),str(R/'analysis/server-latency-20261106-v7'),str(R),str(R/'tools'),str(R/'tools/pylibs'),str(R/'tools/launcher_testdeps'),str(R/'analysis/town-dungeon-latency-20261105-v6/free-thread-deps')]
import els_server.application,els_server.transport,els_server.friends_bridge
sys.argv=['verify_burst.py','--candidate']
runpy.run_path(str(W.parent/'verify_burst.py'),run_name='__main__')
assert not sys._is_gil_enabled()
for name in ('application','transport','consumable_lane','native_inbox','storage.consumables','domain.consumable_flow','domain.resonance_flow','domain.resonance_allocation_flow','periodic_scheduler'):
 module=sys.modules['els_server.'+name];path=Path(module.__file__).resolve();assert path.is_relative_to(B.resolve()),str(path)
proof=read(output/'burst-candidate.json');assert proof['ok']and proof['cleaned']
(W/'built-runtime-qualification.json').write_bytes((json.dumps(dict(ok=True,exe_sha256=read(D/'build.json')['exe_sha256'],actual_selected_root=str(B),source_files_verified=len(files),nine_modules_loaded_from_selected_tree=True,real_TLS=proof,GIL_enabled=False,natural_GUI=False),indent=2)+'\n').encode())
