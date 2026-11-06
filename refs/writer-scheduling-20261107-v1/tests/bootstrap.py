"""Portable scheduling unit fixture; gameplay dependencies are test doubles.

The four writer/transaction source files run unchanged against real SQLite.
Real reward, owner, receipt and native TLS regressions use the signed runtime
in G:/els/analysis/server-writer-scheduling-20261107-v1 instead of these doubles.
"""
import hashlib,importlib.util,sys,types
from contextlib import nullcontext
from pathlib import Path

ARCHIVE=Path(__file__).resolve().parents[1]
HERE=ARCHIVE.parents[1]/'.runtime-cache/writer-scheduling-unit'
HERE.mkdir(parents=True,exist_ok=True)
SOURCE_BINDINGS={p.relative_to(ARCHIVE/'source').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
    for p in sorted((ARCHIVE/'source').rglob('*.py'))}

def stub(name,**values):
    module=types.ModuleType(name);module.__dict__.update(values)
    sys.modules[name]=module
    return module

stub('els_server',__path__=[])
stub('els_server.storage',__path__=[])
stub('els_server.domain',__path__=[])
stub('els_server.performance',sqlite_observed=lambda **kw:None,
    clock_stage=lambda *a,**kw:nullcontext(),worker_timing=lambda *a,**kw:nullcontext())

class ReadConnections:
    def close(self):pass

class RewardState:
    def __init__(self,path,uid,account_id):self.path=path;self.uid=uid;self.account_id=account_id

stub('els_server.storage.read_scope',ReadConnections=ReadConnections,
    committed_reads=lambda **kw:nullcontext(),canonical_path=lambda p:Path(p).resolve(),
    snapshot_connection=lambda *a,**kw:nullcontext())
stub('els_server.storage.writer_errors',writer_result=lambda future:future.result())
stub('els_server.storage.reward_state',RewardState=RewardState)
stub('els_server.domain.drop_pickup',GROUND_ED=frozenset((1,)))

for name in ('storage.sqlite_timing','storage.death_writer','storage.coin_writer'):
    full='els_server.'+name;path=ARCHIVE/'source'/Path(*full.split('.')).with_suffix('.py')
    spec=importlib.util.spec_from_file_location(full,path)
    module=importlib.util.module_from_spec(spec);sys.modules[full]=module;spec.loader.exec_module(module)
