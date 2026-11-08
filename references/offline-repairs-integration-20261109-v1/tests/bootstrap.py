"""Read only the pinned V114 source and the selected offline overlay."""
from pathlib import Path
import json
import sys

sys.dont_write_bytecode = True
WORK = Path(__file__).resolve().parents[1]
BASE = Path(json.loads((WORK / 'inputs.json').read_bytes())['parent_path'])
sys.path[:0] = [str(BASE),str(BASE/'vendor'),'G:/els/tools/pylibs']
import els_server.domain
import els_server.storage
overlay = WORK / 'source' / 'els_server'
if '--input-candidate' in sys.argv:
    overlay = WORK.with_name('offline-feature-sweep-20261109-v1')/'source'/'els_server'
els_server.domain.__path__.insert(0,str(overlay/'domain'))
els_server.storage.__path__.insert(0,str(overlay/'storage'))
