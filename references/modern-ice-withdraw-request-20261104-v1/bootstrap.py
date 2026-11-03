import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=Path('G:/els')
BASE=ROOT/'releases/online/native-modern-ice-sale-window-20261104-v1'
sys.dont_write_bytecode=True
sys.path[:0]=[str(BASE),str(ROOT/'tools'),str(ROOT/'tools/pylibs')]
import els_server,els_server.domain,els_server.protocol
for module,sub in((els_server,'els_server'),(els_server.domain,'els_server/domain'),(els_server.protocol,'els_server/protocol')):
    module.__path__.insert(0,str(HERE/'candidate'/sub))
