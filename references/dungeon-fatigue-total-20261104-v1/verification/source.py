from pathlib import Path
import json,os,sys,tempfile
HERE=Path(__file__).resolve().parent.parent;CHANNEL='online'
BASE=Path(os.environ['ELS_FATIGUE_TEST_PARENT']).resolve();CANDIDATE=HERE/'source'
assert (BASE/'els_server/data/normal_fatigue.json').is_file(),'Pinned complete parent runtime required'
sys.dont_write_bytecode=True;tempfile.tempdir=os.environ.get('ELS_FATIGUE_TEST_TEMP',str(HERE))
sys.path[:0]=[str(BASE),str(BASE/'tools'),str(BASE/'tools/pylibs')]
import els_server,els_server.domain
els_server.domain.__path__.insert(0,str(CANDIDATE/'els_server/domain'))
