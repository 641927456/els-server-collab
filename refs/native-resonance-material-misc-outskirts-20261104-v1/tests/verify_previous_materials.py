import runtime_inputs
import hashlib,importlib.util,io,json,sys,time,unittest
from pathlib import Path
W=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('previous_material_checks',W.parent/'new-role-materials-outskirts-20261104-v1/verify_feedback.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
suite=unittest.TestSuite(t for t in unittest.defaultTestLoader.loadTestsFromTestCase(m.Feedback)if t._testMethodName.startswith(('test_shared_','test_solo_bundle_')))
out=io.StringIO();result=unittest.TextTestRunner(stream=out,verbosity=2).run(suite)
(W/('previous-materials-'+str(time.time_ns())+'.json')).write_text(json.dumps(dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),output=out.getvalue(),details=m.DETAILS,manifest_sha256=hashlib.sha256((W/'candidate-manifest.json').read_bytes()).hexdigest(),previous_tester_sha256=hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()),ensure_ascii=False,indent=2),encoding='utf8')
print(out.getvalue());sys.exit(not result.wasSuccessful())
