"""Changed mount wire/registry consumers only; prior fixture corrections reused."""
from pathlib import Path
import hashlib,importlib.util,io,json,sys,tempfile,unittest
ROOT=Path('G:/els');W=Path(__file__).resolve().parent;B=ROOT/'analysis/pr771-firstbatch-20261103-v1';R=B/'runtime';G=B/'git'
OLD=ROOT/'analysis/pr771-racing-local-20261103-v1'
sys.path[:0]=[str(R),str(OLD),str(OLD/'test-libs')]
import els_server,test_racing
assert Path(els_server.__file__).is_relative_to(R)
(W/'tmp').mkdir(exist_ok=True);tempfile.tempdir=str(W/'tmp')
modules={};hashes={}
for name in ('test_mount_state','test_mount_flow','test_mount_retry'):
    path=G/'tests'/(name+'.py');spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);modules[name]=m;hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
class CurrentFlow(modules['test_mount_flow'].MountFlowTests):
    def setUp(self):
        super().setUp();self.session.handle=self.session._handle
suite=unittest.TestSuite()
for name in unittest.defaultTestLoader.getTestCaseNames(modules['test_mount_state'].MountTests):
    if name!='test_rule_replay_matches_native_and_rejects_nan':suite.addTest(modules['test_mount_state'].MountTests(name))
suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(CurrentFlow))
suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(modules['test_mount_retry'].MountRetryTests))
suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(test_racing.Persistence))
stream=io.StringIO();run=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
paths={n:str(m.__file__)for n,m in sys.modules.copy().items()if n.startswith('els_server')and getattr(m,'__file__',None)}
assert all(Path(p).is_relative_to(R)for p in paths.values())
files=['els_server/'+s for s in ('protocol/mount_messages.py','domain/inventory_items.py','domain/companion_flow.py','domain/mount_racing_items.py','data/mount_racing_items.json','domain/mount_reset_flow.py','storage/mount_reset.py')]
out=dict(ok=run.wasSuccessful(),tests=run.testsRun,skipped=len(run.skipped),errors=[(str(t),s)for t,s in run.errors+run.failures],
    test_hashes=hashes,old_growth_test_sha256=hashlib.sha256((OLD/'test_racing.py').read_bytes()).hexdigest(),
    source_hashes={p:hashlib.sha256((R/p).read_bytes()).hexdigest()for p in files},
    import_paths_verified=True,reused_fixture_corrections=True,installed=False)
(W/'regressions.json').write_bytes((json.dumps(out,indent=2)+'\n').encode());print(stream.getvalue());print(json.dumps(out));sys.exit(not out['ok'])
