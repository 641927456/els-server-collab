"""Run only existing mount persistence/flow/receipt cases affected by this delta."""
from pathlib import Path
import hashlib,importlib.util,io,json,sys,tempfile,unittest
ROOT=Path('G:/els');W=Path(__file__).resolve().parent;R=ROOT/'analysis/pr771-firstbatch-20261103-v1/runtime';G=R.parent/'git'
sys.path.insert(0,str(R))
(W/'test-temp').mkdir(exist_ok=True);tempfile.tempdir=str(W/'test-temp')
import els_server
assert Path(els_server.__file__).resolve().is_relative_to(R)
suite=unittest.TestSuite();test_hashes={}
modules={}
for name in ('test_mount_state','test_mount_flow','test_mount_retry'):
    path=G/'tests'/(name+'.py');spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    modules[name]=module
    suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module));test_hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
if sys.argv[1:]==['failed-only']:
    class NativeStamina(modules['test_mount_state'].MountTests):
        def test_rule_replay_matches_native_and_rejects_nan(self):
            from els_server.domain.mount_rules import advance,catalog
            proof=R/'analysis/mount-combat-20261015/native-stamina-proof.json'
            unit=next(int(k)for k,v in catalog()['templates'].items()if v['recovery_rate']==120)
            for case in json.loads(proof.read_bytes())['cases']:
                self.assertAlmostEqual(advance(unit if case['recovery_rate']==120 else 105,case['initial'],case['seconds'],case['ridden']),case['result'],places=5)
            for stamina in (float('nan'),float('inf'),-1,121):
                with self.assertRaises(ValueError):advance(105,stamina,1,True)
    class CurrentHooks(modules['test_mount_flow'].MountFlowTests):
        def setUp(self):
            super().setUp()
            # Existing observer notices precede the inner gameplay reply.
            # The original case asserts only the mount hook and exhaustion.
            self.session.handle=self.session._handle
    suite=unittest.TestSuite([NativeStamina('test_rule_replay_matches_native_and_rejects_nan'),CurrentHooks('test_session_hooks_when_installed')])
stream=io.StringIO();run=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
from els_server.protocol import mount_messages
from els_server.storage import mount_state
assert Path(mount_messages.__file__).resolve().is_relative_to(R)and Path(mount_state.__file__).resolve().is_relative_to(R)
out=dict(ok=run.wasSuccessful(),tests=run.testsRun,skipped=len(run.skipped),
    failures=[str(x[0])+': '+x[1]for x in run.failures+run.errors],test_hashes=test_hashes,
    source_hashes={p:hashlib.sha256((R/p).read_bytes()).hexdigest()for p in
      ('els_server/storage/mount_state.py','els_server/protocol/mount_messages.py','els_server/domain/mount_racing_rules.py','els_server/storage/mount_growth.py','els_server/data/mount_racing_local.json')},
    runtime_import_paths_verified=True,installed=False)
out['fixture_changes']='Actual private runtime resource path; inner gameplay dispatch for the mount-only assertion'if sys.argv[1:]else None
(W/('affected-tests-final-two.json'if sys.argv[1:]else'affected-tests.json')).write_bytes((json.dumps(out,indent=2)+'\n').encode());print(stream.getvalue());print(json.dumps(out));sys.exit(not out['ok'])
