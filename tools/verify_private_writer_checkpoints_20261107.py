"""Verify private-writer source bindings and run isolated real-SQLite tests."""
import ast,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];A=ROOT/'refs/private-writer-checkpoints-20261107-v1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def main():
    binding=read(A/'source-bindings.json');assert len(binding['files'])==6 and len(binding['inherited'])==2
    assert binding['parent_git']=='84ec1246199ed9b0e54085f733ca12c58a44d0d9'and binding['production_installed']is False
    for name,row in binding['files'].items():
        source=A/'source'/name;parent=ROOT/row.get('parent_source',row.get('parent_git_file'))
        assert source.resolve().is_relative_to((A/'source').resolve())and parent.resolve().is_relative_to(ROOT.resolve())
        assert sha(source)==row['after']and sha(parent)==row['before'];ast.parse(source.read_bytes())
    for group in ('inherited','unit_dependencies'):
        for row in binding[group].values():
            p=ROOT/row['source'];assert p.resolve().is_relative_to(ROOT.resolve())and sha(p)==row['sha256']
    expected={'candidate/'+n:r['after']for n,r in binding['files'].items()}
    expected.update({'candidate/'+n:r['sha256']for n,r in binding['inherited'].items()})
    unit=read(A/'private-writer-checkpoints-tests.json');assert unit['passed']and unit['tests']==8 and not unit['GIL_enabled']
    assert unit['source']==expected
    for name in ('coin-writer-tests.json','coin-writer-lifetime-tests.json','death-ready-writer-tests.json'):
        assert read(A/name)['passed']
    reused=read(A/'financial-reuse.json')
    for run in reused['native_runs'].values():
        assert not run['GIL_enabled']and run['owned_runtime_removed']and run['connections']==0
        for name in reused['unchanged_economic_sources']:
            assert run['candidate_bindings']['candidate/'+name]==expected['candidate/'+name]
    native=read(A/'local-native-current50-five.json')
    assert native['passed']and not native['online_capacity_qualified']and native['seconds']==300
    assert native['source']==expected and native['actors']==dict(town=20,dungeon=30,total=50,native_frontends=0)
    assert native['cold_currency_and_ACK_exact']and native['final_town_SQL_coordinates_exact']
    assert native['owned_runtime_removed']and not native['connections']and not native['errors']
    script=A/'tests/test_private_writer_checkpoints.py'
    runner="import sys,runpy;sys.path.insert(0,sys.argv.pop(1));runpy.run_path(sys.argv.pop(1),run_name='__main__')"
    subprocess.run([sys.executable,'-B','-c',runner,str(script.parent),str(script)],check=True)
    print(json.dumps(dict(ok=True,changed_sources=6,private_writer_SQLite_tests=8,online_capacity_qualified=False)))
if __name__=='__main__':main()
