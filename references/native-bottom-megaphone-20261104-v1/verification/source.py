"""Reproduce tests with a complete matching private parent; no production writes."""
import hashlib,json,os,sys
from pathlib import Path
ARCHIVE=Path(__file__).resolve().parent.parent;CHANNEL=sys.argv[1]
assert CHANNEL=='online','Only ONLINE was installed in this batch'
BASE=Path(os.environ['ELS_ANNOUNCEMENT_TEST_PARENT']).resolve()
HERE=Path(os.environ['ELS_ANNOUNCEMENT_TEST_TEMP']).resolve();HERE.mkdir(parents=True,exist_ok=True)
CANDIDATE=ARCHIVE/'source/online';contract=json.loads((ARCHIVE/'source-contract.json').read_bytes())
for name,row in contract['files'].items():
 p=BASE/name;assert(hashlib.sha256(p.read_bytes()).hexdigest()if p.is_file()else None)==row['parent_sha256'],name
sys.dont_write_bytecode=True;sys.path[:0]=[str(BASE),str(BASE/'tools'),str(BASE/'tools/pylibs')]
import els_server,els_server.domain,els_server.protocol
els_server.domain.__path__.insert(0,str(CANDIDATE/'els_server/domain'))
els_server.protocol.__path__.insert(0,str(CANDIDATE/'els_server/protocol'))
