from pathlib import Path
import ctypes,sys
F=Path(__file__).resolve().parent;R=Path('G:/els');B=R/'releases/online/native-achievement-equipped-set-history-20261107-v2'
Q=F/'qa-source-tree';assert(Q/'owner.json').exists()
sys.dont_write_bytecode=True;sys.path[:0]=[str(Q),str(Q/'vendor'),str(Q/'tools'),str(R/'tools/pylibs'),str(R)]
if sys.version_info[:2]==(3,14):ctypes.WinDLL(str(Q/'python/sqlite3.dll'))
