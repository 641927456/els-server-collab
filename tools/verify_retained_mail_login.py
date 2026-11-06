"""Verify the installed source archive; optionally run synthetic mail regressions."""
from pathlib import Path
import argparse,ast,hashlib,json,os,subprocess,sys

ROOT=Path(__file__).resolve().parents[1]
REFERENCE=ROOT/'references/retained-mail-login-20261101-v1'

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,help='Existing qualified runtime and static assets; no live saves are read')
    parser.add_argument('--channel',choices=('online','local'),default='online')
    args=parser.parse_args()
    manifest=json.loads((REFERENCE/'manifest.json').read_bytes())
    expected={'els_server/storage/mail_attachments.py','els_server/storage/item_instances.py','els_server/protocol/mail_notifications_2026.py'}
    changed={row['path']for row in manifest['files']if not row['existing_runtime_dependency']}
    assert changed==expected and manifest['changed_runtime_files']==3
    assert len(manifest['files'])==5 and len({r['path']for r in manifest['files']})==5
    for row in manifest['files']:
        path=(ROOT/row['source']).resolve()
        assert path.is_relative_to((REFERENCE/'source').resolve())
        assert path.stat().st_size==row['size']and digest(path)==row['sha256'],row['path']
        if path.suffix=='.py':ast.parse(path.read_text('utf8'))
    data=json.loads((REFERENCE/'source/els_server/data/retained_native_consumables.json').read_bytes())
    assert data['new_sources']is False and data['consumption_enabled']is False
    qualification=json.loads((REFERENCE/'qualification.json').read_bytes())
    assert qualification['synthetic_tests_passed']==7 and qualification['public_protocol']['request_count']==39
    assert qualification['public_protocol']['cold_authenticated_reconnect']and not qualification['natural_GUI']
    if args.runtime:
        runtime=args.runtime.resolve()
        for row in manifest['files']+manifest['runtime_context'][args.channel]:
            assert digest(runtime/row['path'])==row['sha256'],'Qualified runtime differs: '+row['path']
        env=dict(os.environ,ELS_RETAINED_MAIL_RUNTIME=str(runtime),ELS_RETAINED_MAIL_TEST_HOME=str(ROOT/'.runtime-cache/retained-mail-login-tests'))
        subprocess.run([sys.executable,'-B',str(REFERENCE/'runtime_tests.py')],env=env,check=True,cwd=ROOT)
    print(json.dumps(dict(ok=True,changed_runtime_files=3,inherited_dependencies=2,runtime_tests_ran=args.runtime is not None)))

if __name__=='__main__':main()
