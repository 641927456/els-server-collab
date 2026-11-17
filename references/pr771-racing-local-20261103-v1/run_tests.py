from pathlib import Path
import hashlib,importlib.util,io,json,sys,unittest
W=Path(__file__).resolve().parent;ROOT=Path('G:/els')
R=ROOT/'analysis/pr771-firstbatch-20261103-v1/runtime';G=R.parent/'git'
sys.path[:0]=[str(R),str(W),str(W/'test-libs')]
import els_server
assert Path(els_server.__file__).resolve().is_relative_to(R)
import test_racing
names=sys.argv[1:]
suite=unittest.defaultTestLoader.loadTestsFromNames(names,test_racing)if names else unittest.defaultTestLoader.loadTestsFromModule(test_racing)
stream=io.StringIO();run=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
files=['els_server/data/mount_racing_local.json','els_server/domain/mount_racing_rules.py','els_server/storage/mount_growth.py','els_server/storage/mount_state.py','els_server/protocol/mount_messages.py']
import hypothesis
out=dict(ok=run.wasSuccessful(),tests=run.testsRun,skipped=len(run.skipped),failures=[str(x[0])+': '+x[1]for x in run.failures+run.errors],
    source_hashes={f:hashlib.sha256((R/f).read_bytes()).hexdigest()for f in files},test_sha256=hashlib.sha256((W/'test_racing.py').read_bytes()).hexdigest(),
    hypothesis=hypothesis.__version__,generated_examples_per_property=200,properties=2,
    scope='Local calculations and internal complete-profile persistence; no actual race/reset transaction or packet entry',installed=False,natural_GUI=False)
path=W/('tests-final.json'if not names else'tests-selected.json');path.write_bytes((json.dumps(out,indent=2)+'\n').encode())
print(stream.getvalue());print(json.dumps(out));sys.exit(not out['ok'])
