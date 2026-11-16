from pathlib import Path
import hashlib,io,json,sys,unittest
W=Path(__file__).resolve().parent;ROOT=Path('G:/els');R=ROOT/'analysis/pr771-firstbatch-20261103-v1/runtime'
sys.path[:0]=[str(R),str(W)]
import test_reset
names=sys.argv[1:]
suite=unittest.defaultTestLoader.loadTestsFromNames(names,test_reset)if names else unittest.defaultTestLoader.loadTestsFromModule(test_reset)
stream=io.StringIO();run=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
paths=['els_server/'+s for s in ('data/mount_racing_items.json','domain/mount_racing_items.py','domain/inventory_items.py','domain/mount_reset_flow.py','domain/companion_flow.py','protocol/mount_messages.py','storage/mount_reset.py')]
out=dict(ok=run.wasSuccessful(),tests=run.testsRun,skipped=len(run.skipped),errors=[(str(t),s)for t,s in run.errors+run.failures],
    source_hashes={p:hashlib.sha256((R/p).read_bytes()).hexdigest()for p in paths},test_sha256=hashlib.sha256((W/'test_reset.py').read_bytes()).hexdigest(),
    actual_race=False,synthetic_initial_growth=True,original_context_authority=True,installed=False,natural_GUI=False)
target=W/('tests-first.json'if not names else'tests-selected.json');target.write_bytes((json.dumps(out,indent=2)+'\n').encode())
print(stream.getvalue());print(json.dumps(out));sys.exit(not out['ok'])
