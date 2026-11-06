import os,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
BASE=Path(os.environ['ELS_ENTRY_TEST_PARENT']).resolve()
assert (BASE/'els_server/data/normal_fatigue.json').is_file(),'Complete pinned runtime resources are required'
sys.dont_write_bytecode=True
tempfile.tempdir=os.environ.get('ELS_ENTRY_TEST_TEMP',str(HERE))
sys.path.insert(0,str(BASE))
import els_server,els_server.domain,els_server.protocol
els_server.domain.__path__.insert(0,str(HERE.parent/'source/els_server/domain'))
els_server.protocol.__path__.insert(0,str(HERE.parent/'source/els_server/protocol'))
