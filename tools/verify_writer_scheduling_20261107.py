"""Bind the four-leaf candidate and run real-SQLite scheduling unit tests."""
import ast,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
A=ROOT/'refs/writer-scheduling-20261107-v1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    binding=json.loads((A/'source-bindings.json').read_bytes())
    assert binding['parent_git']=='64dc1d510e39b1c3e305616533f60d2300a7efff'
    assert binding['production_installed']is False
    assert len(binding['files'])==4
    for name,row in binding['files'].items():
        source=A/'source'/name;parent=ROOT/row['parent_git_file']
        assert source.resolve().is_relative_to((A/'source').resolve())
        assert parent.resolve().is_relative_to(ROOT.resolve())
        assert sha(source)==row['after']and sha(parent)==row['before']
        ast.parse(source.read_bytes(),filename=str(source))
    for name in ('writer-scheduling-tests.json','death-ready-writer-tests.json',
            'coin-writer-tests.json','coin-writer-lifetime-tests.json','late-batch-candidate.json'):
        receipt=json.loads((A/name).read_bytes());assert receipt['passed']
    unit=json.loads((A/'writer-scheduling-tests.json').read_bytes())
    assert {n.removeprefix('candidate/'):v for n,v in unit['candidate'].items()}=={
        n:r['after']for n,r in binding['files'].items()}
    assert unit['tests']==3 and len(unit['scenarios'])==2
    native=json.loads((A/'local-native40-five-summary.json').read_bytes())
    assert native['passed']and native['source_bindings']=={n:r['after']for n,r in binding['files'].items()}
    assert native['workload_seconds_per_actor']==300 and native['actors']==dict(town=20,dungeon=20,total=40,native_frontends=0)
    assert native['owned_runtime_removed']and not native['connections']and not native['errors']
    assert native['durable_currency_and_ACK_exact']and native['final_town_SQL_coordinates_exact']
    assert not native['online_capacity_qualified']and not native['GIL_enabled']
    # Dedicated child: dependency doubles never enter other CI test modules.
    script=A/'tests/test_writer_scheduling.py'
    runner="import sys,runpy;sys.path.insert(0,sys.argv.pop(1));runpy.run_path(sys.argv.pop(1),run_name='__main__')"
    subprocess.run([sys.executable,'-B','-c',runner,str(script.parent),str(script)],check=True)
    print(json.dumps(dict(ok=True,source_files=4,portable_real_SQLite_tests=3,
        reward_and_native_evidence_separate=True,production_installed=False)))

if __name__=='__main__':main()
