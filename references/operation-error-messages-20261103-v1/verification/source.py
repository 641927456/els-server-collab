import json,os,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
BASE=Path(os.environ['ELS_OPERATION_TEST_PARENT']).resolve()
sys.dont_write_bytecode=True;tempfile.tempdir=os.environ.get('ELS_OPERATION_TEST_TEMP',str(HERE))
sys.path.insert(0,str(BASE))
import els_server,els_server.domain,els_server.storage
els_server.domain.__path__.insert(0,str(HERE.parent/'source/els_server/domain'))
els_server.storage.__path__.insert(0,str(HERE.parent/'source/els_server/storage'))
