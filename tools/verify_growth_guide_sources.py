"""Verify the finite, unselected #727 archive without private runtime assets."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,sys,tempfile

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'references/growth-guide-permanent-20261101-v1'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--with-runtime',action='store_true');args=parser.parse_args()
    contract=json.loads((BASE/'source-contract.json').read_bytes())
    assert contract['candidate_only'] and not contract['installed'] and not contract['root_runtime_changed']
    assert contract['issue']==727 and contract['delivery_blockers']
    files=contract['files'];assert len(files)==len({r['path']for r in files})
    for row in files:
        path=(ROOT/row['source']).resolve();assert path.is_relative_to((BASE/'source').resolve())
        raw=path.read_bytes();assert (len(raw),hashlib.sha256(raw).hexdigest())==(row['size'],row['sha256']),row['path']
        if path.suffix=='.py':compile(raw,str(path),'exec')
        if row['root_parent_sha256'] is not None:
            assert hashlib.sha256((ROOT/row['path']).read_bytes()).hexdigest()==row['root_parent_sha256'],row['path']
        else:assert not(ROOT/row['path']).exists(),row['path']
    folder=BASE/'source/els_server/data'
    for name in ('growth_guide','growth_guide_boxes','growth_guide_stats','equipment_tuning_native'):
        raw=(folder/(name+'.json')).read_bytes();manifest=json.loads((folder/(name+'.manifest.json')).read_bytes())
        assert hashlib.sha256(raw).hexdigest()==manifest['payload_sha256'],name
    guide=json.loads((folder/'growth_guide.json').read_bytes());boxes=json.loads((folder/'growth_guide_boxes.json').read_bytes())
    assert(len(guide['tabs']),len(guide['quests']),len(boxes['boxes']),len(boxes['items']))==(13,61,63,832)
    print(json.dumps(dict(ok=True,candidate_only=True,files=len(files),courses=13,quests=61,boxes=63,installed=False)))
    if args.with_runtime:
        # Only tracked source/config/tests, locked static resources and the two
        # existing private test fixtures enter this disposable server view.
        cache=ROOT/'.runtime-cache';cache.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='growth-guide-',dir=cache) as folder:
            view=Path(folder).resolve();assert view.is_relative_to(cache.resolve())
            paths=subprocess.run(['git','ls-files','-z','--','els_server','config','tests'],cwd=ROOT,capture_output=True,check=True).stdout.decode('utf8').split('\0')
            for name in filter(None,paths):
                dest=view/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,dest)
            locked=json.loads((ROOT/'runtime-assets.lock.json').read_bytes())['files']
            for row in locked:
                if not row['path'].startswith(('els_server/','analysis/')):continue
                source=ROOT/row['path'];raw=source.read_bytes()
                assert (len(raw),hashlib.sha256(raw).hexdigest())==(row['size'],row['sha256']),row['path']
                dest=view/row['path'];dest.parent.mkdir(parents=True,exist_ok=True);os.link(source,dest)
            for name in ('analysis/client-6c6b5180/20261013-160720/death-event-header.json','analysis/runs/20261012-163220-994976/local-bootstrap.json'):
                dest=view/name;dest.parent.mkdir(parents=True,exist_ok=True);os.link(ROOT/name,dest)
            for row in files:
                dest=view/row['path'];dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/row['source'],dest)
            env=dict(os.environ,TEMP=str(view),TMP=str(view),PYTHONPATH=str(view))
            subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','tests.test_growth_guide','tests.test_mount_state','tests.test_mount_retry','-q'],cwd=view,env=env,check=True)

if __name__=='__main__':main()
