from pathlib import Path
import ctypes,sys
HERE=Path(__file__).resolve().parent
BASE=HERE/'full-source-v1';ROOT=Path('G:/els')
sys.dont_write_bytecode=True
ctypes.WinDLL(str(HERE.parent/'duel-wire-v2/full-source/python/sqlite3.dll'))
sys.path[:0]=[str(BASE),str(ROOT/'tools/pylibs'),str(ROOT/'tools'),str(ROOT)]
import els_server,els_server.domain,els_server.protocol,els_server.storage
