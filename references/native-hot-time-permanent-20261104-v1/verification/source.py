"""Run archived business/TLS tests with a complete pinned private parent runtime."""
import hashlib,json,os,sys,tempfile
from pathlib import Path
ARCHIVE=Path(__file__).resolve().parent.parent;CHANNEL=sys.argv[1]
assert CHANNEL in('online','local')
BASE=Path(os.environ['ELS_HOT_TIME_TEST_PARENT']).resolve()
HERE=Path(os.environ['ELS_HOT_TIME_TEST_TEMP']).resolve();HERE.mkdir(parents=True,exist_ok=True)
CANDIDATE=ARCHIVE/'source'/CHANNEL
contract=json.loads((ARCHIVE/'source-contract.json').read_bytes())['channels'][CHANNEL]
assert(BASE/'els_server/protocol/access_event_2026.py').is_file(),'Complete original parent runtime required'
for name,row in contract['files'].items():
 parent=BASE/name
 assert(hashlib.sha256(parent.read_bytes()).hexdigest()if parent.is_file()else None)==row['parent_sha256'],name
sys.dont_write_bytecode=True;tempfile.tempdir=str(HERE)
os.environ.update(TEMP=str(HERE),TMP=str(HERE),PYTHONDONTWRITEBYTECODE='1')
sys.path[:0]=[str(BASE),str(BASE/'tools'),str(BASE/'tools/pylibs')]
import els_server,els_server.domain,els_server.storage
els_server.domain.__path__.insert(0,str(CANDIDATE/'els_server/domain'))
els_server.storage.__path__.insert(0,str(CANDIDATE/'els_server/storage'))
