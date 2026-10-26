"""Fail-closed current source contracts; optional owned TLS/current-role regressions."""
import argparse
import json
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
    parser.add_argument('--assets-root',type=Path,default=ROOT);args=parser.parse_args()
    base=json.loads((ROOT/'channels/server-latency-guards-20261027-v1.json').read_bytes())
    final=json.loads((ROOT/'channels/server-risk-remediation-20261027-v1.json').read_bytes())
    delta=json.loads((ROOT/'references/current-runtime-regression-20261027-v1/delta.json').read_bytes())
    cache=ROOT/'.runtime-cache';cache.mkdir(exist_ok=True)
    tests=('test_server_latency_guards.py','test_native_auxiliary_latency.py','test_request_read_scope.py',
           'test_current_native_title_inputs.py','test_retained_native_hp.py','test_native_hero_inputs.py',
           'test_noncharacter_hp_capture.py','test_current_latency_tls.py','test_friends_server.py')
    for channel in ('online','local'):
        old={e['path']:e for e in base['channels'][channel]['files']}
        new={e['path']:e for e in final['channels'][channel]['files']}
        change=delta['channels'][channel]
        assert {p for p in old.keys()|new.keys()if old.get(p)!=new.get(p)}=={change['path']}
        assert old[change['path']]['sha256']==change['before_sha256']
        assert all(new[change['path']][k]==change[k]for k in ('source','sha256','size'))
        plan(ROOT,final,channel)
        if not args.with_runtime:
            print(json.dumps(dict(ok=True,channel=channel,changed_existing_leaves=1,runtime_tests=False)));continue
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
                result=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-p',test],cwd=view,capture_output=True)
                if result.returncode:
                    sys.stderr.write(result.stderr.decode('utf8',errors='replace')[-12000:]);raise SystemExit(result.returncode)
                print(json.dumps(dict(ok=True,channel=channel,test=test,
                    summary=result.stderr.decode('utf8',errors='replace').splitlines()[-1])))


if __name__=='__main__':main()
