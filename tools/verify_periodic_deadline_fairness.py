"""Exact one-leaf inversion, unchanged parents and real slow-worker fairness."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.materialize_formal_runtime import load_manifest,plan

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--with-runtime',action='store_true');parser.add_argument('--assets-root',type=Path,default=ROOT);args=parser.parse_args()
    folder=ROOT/'references/periodic-deadline-fairness-20261027-v1'
    delta=json.loads((folder/'delta.json').read_bytes());base=load_manifest(ROOT/delta['parent'],ROOT)
    candidate=load_manifest(ROOT/'channels/periodic-deadline-fairness-20261027-v1.json',ROOT)
    old=b'                for slot in list(self.slots.values()):'
    new=b'                for slot in sorted(self.slots.values(), key=lambda value: value.due):'
    for mode in('online','local'):
        before={e['path']:e for e in base['channels'][mode]['files']};after={e['path']:e for e in candidate['channels'][mode]['files']}
        assert {p for p in before.keys()|after.keys()if before.get(p)!=after.get(p)}=={delta['leaf']}
        plan(ROOT,candidate,mode)
        original=(ROOT/before[delta['leaf']]['source']).read_bytes();source=ROOT/after[delta['leaf']]['source'];raw=source.read_bytes()
        assert hashlib.sha256(original).hexdigest()==delta['before_sha256']
        assert hashlib.sha256(raw).hexdigest()==delta['sha256']
        assert original.count(old)==raw.count(new)==1 and raw.replace(new,old)==original
        # Import the exact selected pure scheduler module, with no fake scheduler
        # or player database; only the asynchronous business latency is a fixture.
        code="""import importlib.util,pathlib,sys,unittest
root=pathlib.Path(sys.argv[1]);source=pathlib.Path(sys.argv[2]);sys.path.insert(0,str(root))
name='els_server.periodic_scheduler';spec=importlib.util.spec_from_file_location(name,source);mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod)
assert pathlib.Path(mod.__file__).resolve()==source.resolve()
suite=unittest.defaultTestLoader.loadTestsFromName('tests.test_periodic_deadline_fairness')
result=unittest.TextTestRunner().run(suite);assert result.testsRun==2;sys.exit(not result.wasSuccessful())
"""
        subprocess.run([sys.executable,'-B','-c',code,str(ROOT),str(source)],cwd=ROOT,check=True)
        print(json.dumps(dict(ok=True,mode=mode,changed_existing_runtime_leaves=1,source_inverse=True,slow_worker_tests=2,no_economic_or_player_requests=True)))
    if args.with_runtime:
        subprocess.run([sys.executable,'-B',str(ROOT/'tools/verify_initialization_readers.py'),'--with-runtime','--assets-root',str(args.assets_root),'--manifest',str(ROOT/'channels/periodic-deadline-fairness-20261027-v1.json'),'--delta',str(folder/'delta.json')],cwd=ROOT,check=True)

if __name__=='__main__':main()
