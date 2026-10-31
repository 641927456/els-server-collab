"""Fail-closed current source contracts; optional owned TLS/current-role regressions."""
import argparse
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.materialize_formal_runtime import materialize,plan


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--with-runtime',action='store_true')
    parser.add_argument('--assets-root',type=Path,default=ROOT)
    parser.add_argument('--manifest',type=Path,default=ROOT/'channels/server-architecture-20261027-v1.json')
    parser.add_argument('--delta',type=Path,default=ROOT/'references/server-architecture-20261027-v1/delta.json')
    args=parser.parse_args()
    final=json.loads(args.manifest.read_bytes())
    delta=json.loads(args.delta.read_bytes())
    from tools.materialize_formal_runtime import bound
    base=json.loads(bound(ROOT,delta['parent']).read_bytes())
    cache=ROOT/'.runtime-cache';cache.mkdir(exist_ok=True)
    tests=('test_server_latency_guards.py','test_native_auxiliary_latency.py','test_request_read_scope.py',
           'test_current_native_title_inputs.py','test_retained_native_hp.py','test_native_hero_inputs.py',
           'test_noncharacter_hp_capture.py','test_current_latency_tls.py','test_friends_server.py')
    tests=tests[:-1]+('test_local_auxiliary_roles.py','test_architecture_scheduler.py','test_architecture_tls.py','test_registration.py',tests[-1])
    for channel in ('online','local'):
        old={e['path']:e for e in base['channels'][channel]['files']}
        new={e['path']:e for e in final['channels'][channel]['files']}
        changes=delta['channels'][channel]
        if 'path' in changes:changes={changes['path']:changes}
        assert {p for p in old.keys()|new.keys()if old.get(p)!=new.get(p)}==set(changes)
        for path,change in changes.items():
            assert (old[path]['sha256']if path in old else None)==change['before_sha256']
            assert all(new[path][k]==change[k]for k in ('source','sha256','size'))
        plan(ROOT,final,channel)
        if not args.with_runtime:
            print(json.dumps(dict(ok=True,channel=channel,delta_leaves=len(changes),runtime_tests=False)));continue
        with tempfile.TemporaryDirectory(prefix='current-regression-',dir=cache)as folder:
            view=Path(folder)/'engine'
            materialize(ROOT,final,channel,view,assets_root=args.assets_root,link_assets=True)
            (view/'tests').mkdir();(view/'tools').mkdir()
            for test in tests:shutil.copyfile(ROOT/'tests'/test,view/'tests'/test)
            for tool in ('create_friends_certificate.py','import_friends_save.py'):
                shutil.copyfile(ROOT/'tools'/tool,view/'tools'/tool)
            (view/'docs').mkdir()
            shutil.copyfile(ROOT/'docs/client-first-monster-inputs-20261026.json',view/'docs/client-first-monster-inputs-20261026.json')
            # Run explicit modules: the old full Friends suite remains a
            # separately classified legacy suite; never silently include it.
            for test in tests[:-1]:
                runner=("import sys,unittest;from pathlib import Path;"
                        "root=Path(sys.argv[1]).resolve();sys.path.insert(0,str(root));"
                        "import els_server;assert Path(els_server.__file__).resolve().is_relative_to(root);"
                        "suite=unittest.defaultTestLoader.discover(str(root/'tests'),pattern=sys.argv[2]);"
                        "result=unittest.TextTestRunner().run(suite);sys.exit(not result.wasSuccessful())")
                result=subprocess.run([sys.executable,'-B','-c',runner,str(view),test],cwd=view,capture_output=True)
                if result.returncode:
                    sys.stderr.write(result.stderr.decode('utf8',errors='replace')[-12000:]);raise SystemExit(result.returncode)
                stderr=result.stderr.decode('utf8',errors='replace')
                count=re.search(r'Ran (\d+) tests?',stderr)
                print(json.dumps(dict(ok=True,channel=channel,test=test,test_count=int(count[1]),summary=stderr.splitlines()[-1])))


if __name__=='__main__':main()
