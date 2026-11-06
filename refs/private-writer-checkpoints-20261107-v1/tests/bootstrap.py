"""Portable real-SQLite policy tests; gameplay dependencies are explicit doubles."""
import hashlib,importlib.util,json,sqlite3,sys,types
from contextlib import nullcontext,closing,contextmanager
from pathlib import Path
A=Path(__file__).resolve().parents[1];ROOT=A.parents[1]
HERE=ROOT/'.runtime-cache/private-writer-checkpoint-unit';HERE.mkdir(parents=True,exist_ok=True)
B=json.loads((A/'source-bindings.json').read_bytes())
SOURCE_BINDINGS={'candidate/'+n:r['after']for n,r in B['files'].items()}
SOURCE_BINDINGS.update({'candidate/'+n:r['sha256']for n,r in B['inherited'].items()})
def stub(name,**values):
    module=types.ModuleType(name);module.__dict__.update(values);sys.modules[name]=module;return module
stub('els_server',__path__=[]);stub('els_server.storage',__path__=[]);stub('els_server.domain',__path__=[])
stub('els_server.performance',sqlite_observed=lambda **kw:None,clock_stage=lambda *a,**kw:nullcontext(),worker_timing=lambda *a,**kw:nullcontext())
class ReadConnections:
    def close(self):pass
class RewardState:
    def __init__(self,path,uid,account_id):self.path=path;self.uid=uid;self.account_id=account_id
@contextmanager
def snapshot(path,**kwargs):
    with closing(sqlite3.connect(Path(path).as_uri()+'?mode=ro',uri=True))as db:yield db
stub('els_server.storage.read_scope',ReadConnections=ReadConnections,committed_reads=lambda **kw:nullcontext(),canonical_path=lambda p:Path(p).resolve(),snapshot_connection=snapshot)
stub('els_server.storage.reward_state',RewardState=RewardState)
stub('els_server.domain.drop_pickup',GROUND_ED=frozenset((1,)))
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module;spec.loader.exec_module(module)
load('els_server.storage.writer_errors',ROOT/B['unit_dependencies']['els_server/storage/writer_errors.py']['source'])
load('els_server.storage.sqlite_timing',ROOT/B['inherited']['els_server/storage/sqlite_timing.py']['source'])
load('els_server.storage.town_position_buffer',ROOT/B['unit_dependencies']['els_server/storage/town_position_buffer.py']['source'])
for leaf in ('wal_checkpoints','coin_writer','death_writer','clock_writer','position_writer'):
    load('els_server.storage.'+leaf,A/'source/els_server/storage'/(leaf+'.py'))
