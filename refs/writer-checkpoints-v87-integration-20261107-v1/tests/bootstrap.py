"""Native tests against an explicitly supplied, pinned V87 software runtime."""
import ctypes,hashlib,importlib.abc,importlib.machinery,importlib.util,json,os,sys
from pathlib import Path
A=Path(__file__).resolve().parents[1];ROOT=A.parents[1]
B=json.loads((A/'source-bindings.json').read_bytes())
if '--runtime-parent'not in sys.argv:raise RuntimeError('Supply --runtime-parent with the pinned V87 software release directory')
BASE=Path(sys.argv[sys.argv.index('--runtime-parent')+1]).resolve()
assert hashlib.sha256((BASE/'rollup-manifest.json').read_bytes()).hexdigest()==B['runtime_parent_manifest_sha256']
HERE=ROOT/'.runtime-cache/anniversary-read-first';HERE.mkdir(parents=True,exist_ok=True)
os.environ.update(TEMP=str(HERE),TMP=str(HERE),PYTHONDONTWRITEBYTECODE='1')
sys.dont_write_bytecode=True
sys.path[:0]=[str(BASE),str(BASE/'vendor'),str(ROOT),str(ROOT/'tools/pylibs')]
assert 'sqlite3'not in sys.modules
_sqlite=ctypes.WinDLL(str(BASE/'python/sqlite3.dll'))
import sqlite3
assert sqlite3.sqlite_version=='3.54.1'
SOURCE_BINDINGS={'candidate/'+n:r['sha256']for n,r in B['files'].items()}
if '--baseline'not in sys.argv:
    class Loader(importlib.machinery.SourceFileLoader):
        def exec_module(self,module):
            module.__file__=str(BASE/Path(*module.__name__.split('.')).with_suffix('.py'))
            exec(self.get_code(module.__name__),module.__dict__)
    class Finder(importlib.abc.MetaPathFinder):
        def find_spec(self,fullname,path=None,target=None):
            row=B['files'].get(fullname.replace('.','/')+'.py')
            if row is None:return None
            source=ROOT/row['source']
            assert hashlib.sha256(source.read_bytes()).hexdigest()==row['sha256']
            return importlib.util.spec_from_file_location(fullname,source,loader=Loader(fullname,str(source)))
    sys.meta_path.insert(0,Finder())
