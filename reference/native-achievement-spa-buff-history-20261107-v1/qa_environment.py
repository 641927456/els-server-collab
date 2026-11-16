"""Only the isolated candidate imports these overrides; installed files stay frozen."""
from pathlib import Path
import ctypes,sys
F=Path(__file__).resolve().parent;R=Path('G:/els')
B=R/'releases/online/native-achievement-social-enhancement-history-20261107-v1'
sys.dont_write_bytecode=True
sys.path[:0]=[str(B),str(B/'vendor'),str(B/'tools'),str(R/'tools/pylibs'),str(R),
    str(R/'analysis/pr771-racing-local-20261103-v1/test-libs')]
if sys.version_info[:2]==(3,14):ctypes.WinDLL(str(B/'python/sqlite3.dll'))
import els_server.domain,els_server.storage
els_server.domain.__path__.insert(0,str(F/'source-v1/els_server/domain'))
els_server.storage.__path__.insert(0,str(F/'source-v1/els_server/storage'))

