from pathlib import Path
import ctypes,sys
F=Path(__file__).resolve().parent;R=Path('G:/els');B=R/'releases/online/native-altera-mine-retirement-20261107-v1'
sys.dont_write_bytecode=True;sys.path[:0]=[str(B),str(B/'vendor'),str(B/'tools'),str(R/'tools/pylibs'),str(R),str(R/'analysis/pr771-racing-local-20261103-v1/test-libs')]
if sys.version_info[:2]==(3,14):ctypes.WinDLL(str(B/'python/sqlite3.dll'))
import els_server.domain,els_server.storage
for package,suffix in((els_server.domain,'domain'),(els_server.storage,'storage')):
    package.__path__.insert(0,str(F.parent/'equipment-set-history-v1/source-v1/els_server'/suffix))
    package.__path__.insert(0,str(F/'source-v1/els_server'/suffix))
