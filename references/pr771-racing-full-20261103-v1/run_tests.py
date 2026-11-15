"""Run the requested affected cases against the isolated candidate only."""
from pathlib import Path
import hashlib,importlib.util,io,json,sys,tempfile,unittest
ROOT=Path('G:/els');W=Path(__file__).resolve().parent;B=ROOT/'analysis/pr771-firstbatch-20261103-v1';R=B/'runtime';G=B/'git'
sys.path[:0]=[str(W),str(R),str(B),str(ROOT/'analysis/pr771-racing-local-20261103-v1/test-libs')]
(W/'tmp').mkdir(exist_ok=True);tempfile.tempdir=str(W/'tmp')
from source_set import sources
class Result(unittest.TextTestResult):
    def startTest(self,test):super().startTest(test);self.current=str(test)
    def addSuccess(self,test):super().addSuccess(test);passed.append(str(test))
passed=[];suite=unittest.TestSuite()
for name in sys.argv[2:]:suite.addTests(unittest.defaultTestLoader.loadTestsFromName(name))
stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2,resultclass=Result).run(suite)
paths={n:str(m.__file__)for n,m in sys.modules.copy().items()if n.startswith('els_server')and getattr(m,'__file__',None)}
assert all(Path(p).is_relative_to(R)for p in paths.values())
tests={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in W.glob('test_*.py')}
out=dict(ok=result.wasSuccessful(),tests=result.testsRun,passed=passed,skipped=len(result.skipped),
         errors=[(str(t),s)for t,s in result.errors+result.failures],source_hashes=sources(),test_hashes=tests,
         import_paths_verified=True,private_fixture=True,installed=False,natural_GUI=False)
(W/(sys.argv[1]+'.json')).write_text(json.dumps(out,indent=2)+'\n',encoding='utf8')
print(stream.getvalue());print(json.dumps(dict(report=sys.argv[1],ok=out['ok'],tests=out['tests'],errors=len(out['errors']))));sys.exit(not out['ok'])
