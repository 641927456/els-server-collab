from pathlib import Path
import sys
F=Path(__file__).resolve().parent;R=Path('G:/els')
B=R/'releases/local/unified-server-a73aa07d02be0f86-95d9837f961b'
sys.dont_write_bytecode=True
sys.path[:0]=[str(B),str(B/'vendor'),str(B/'tools'),str(R/'tools/pylibs'),str(R/'tools'),str(R)]
import els_server.domain,els_server.storage,els_server.protocol
for package,name in((els_server.domain,'domain'),(els_server.storage,'storage'),(els_server.protocol,'protocol')):
 package.__path__.insert(0,str(F/'source-v1/els_server'/name))
