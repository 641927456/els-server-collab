"""Pinned ONLINE source with a task-owned optional source overlay."""
import hashlib,importlib.abc,importlib.machinery,importlib.util,json,os,sys,sysconfig,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=Path('G:/els')
def candidate_bindings():
 return{str(p.relative_to(HERE)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()for p in sorted((HERE/'candidate').rglob('*'))if p.suffix in('.py','.dll')}
SOURCE_BINDINGS=candidate_bindings()
PIN=json.loads((HERE/'baseline.json').read_bytes());BASE=Path(PIN['parent_path'])
assert hashlib.sha256((BASE/'rollup-manifest.json').read_bytes()).hexdigest()==PIN['parent_manifest_sha256']
import ctypes
assert 'sqlite3'not in sys.modules
_sqlite_runtime=ctypes.WinDLL(str(BASE/'python/sqlite3.dll'))
import sqlite3
assert sqlite3.sqlite_version=='3.54.1'
sys.dont_write_bytecode=True
os.environ.update(TEMP=str(HERE),TMP=str(HERE),PYTHONDONTWRITEBYTECODE='1')
tempfile.tempdir=str(HERE)
sys.path[:0]=[str(HERE),str(ROOT/'analysis/server-latency-20261106-v7'),str(BASE),str(ROOT),str(ROOT/'tools'),str(ROOT/'tools/pylibs'),str(ROOT/'tools/launcher_testdeps')]
FREE_THREADED_BUILD=sysconfig.get_config_var('Py_GIL_DISABLED')==1
if FREE_THREADED_BUILD:sys.path.insert(0,str(ROOT/'analysis/town-dungeon-latency-20261105-v6/free-thread-deps'))
if '--candidate' in sys.argv:
 class Loader(importlib.machinery.SourceFileLoader):
  def exec_module(self,module):
   # Resources stay at the pinned ONLINE path, without copying its data tree.
   module.__file__=str(BASE/Path(*module.__name__.split('.')).with_suffix('.py'))
   exec(self.get_code(module.__name__),module.__dict__)
 class Finder(importlib.abc.MetaPathFinder):
  def find_spec(self,fullname,path=None,target=None):
   source=HERE/'candidate'/Path(*fullname.split('.')).with_suffix('.py')
   if source.is_file():return importlib.util.spec_from_file_location(fullname,source,loader=Loader(fullname,str(source)))
 sys.meta_path.insert(0,Finder())
import els_server.application,els_server.transport,els_server.friends_bridge
if FREE_THREADED_BUILD and sys._is_gil_enabled():raise RuntimeError('A runtime dependency re-enabled the GIL')
