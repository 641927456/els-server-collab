import hashlib,json,os,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
BASE=Path(os.environ['ELS_ERP_TEST_PARENT']).resolve()
contract=json.loads((HERE.parent/'source-contract.json').read_bytes())
for name,expected in contract['unchanged_test_resources'].items():
 raw=(BASE/name).read_bytes();assert hashlib.sha256(raw).hexdigest()==expected
 p=HERE.parent/'source'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
sys.dont_write_bytecode=True;tempfile.tempdir=os.environ.get('ELS_ERP_TEST_TEMP',str(HERE))
sys.path.insert(0,str(BASE))
import els_server,els_server.domain,els_server.protocol,els_server.storage
for package in(els_server.domain,els_server.protocol,els_server.storage):package.__path__.insert(0,str(HERE.parent/'source/els_server'/package.__name__.rsplit('.',1)[-1]))
