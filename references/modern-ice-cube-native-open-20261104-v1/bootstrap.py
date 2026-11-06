from pathlib import Path
import sys
ROOT=Path('G:/els');HERE=Path(__file__).resolve().parent;BASE=ROOT/'releases/online/native-dungeon-business-isolation-20261104-v2'
sys.dont_write_bytecode=True
sys.path[:0]=[str(BASE),str(ROOT/'tools'),str(ROOT/'tools/pylibs')]

import els_server.storage,els_server.domain
if '--candidate' in sys.argv:
 els_server.storage.__path__.insert(0,str(HERE/'candidate/els_server/storage'))
 els_server.domain.__path__.insert(0,str(HERE/'candidate/els_server/domain'))
