from pathlib import Path
import ctypes,os,sys
HERE=Path(__file__).resolve().parent
BASE=Path(os.environ['ELS_FULL_SOURCE']).resolve()
ROOT=Path('G:/els')
sys.dont_write_bytecode=True
ctypes.WinDLL(str(BASE/'python/sqlite3.dll'))
sys.path[:0]=[str(BASE),str(BASE/'vendor'),str(ROOT/'tools/pylibs'),str(ROOT/'tools'),str(ROOT)]
import els_server,els_server.domain,els_server.protocol,els_server.storage
if '--entry-baseline'in sys.argv:els_server.domain.__path__.insert(0,str(HERE/'baseline/els_server/domain'))
