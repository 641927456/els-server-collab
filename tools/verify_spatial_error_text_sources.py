"""Verify exact installed source archives and portable scene-error contracts."""
from pathlib import Path
import ast,hashlib,importlib.util,json,subprocess,sys

ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=ROOT/'references/spatial-error-text-20261101-v1'

def main():
    data=json.loads((ARCHIVE/'source-contract.json').read_bytes())
    assert data['schema']==1 and data['source_archive_only'] is True
    assert data['client_changes']==0 and not data['new_schema'] and not data['qualification_changes']
    assert not data['natural_GUI'] and data['launcher_selected_local'] and data['QA_cleaned']
    spec=importlib.util.spec_from_file_location('spatial_error_guard',ARCHIVE/'validation/check_spatial_error_codes.py')
    guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
    unique=set();count=0
    for mode in ('online','local'):
        channel=data['channels'][mode];rows=channel['changes']
        assert len(rows)==5 and len({row['path']for row in rows})==5
        assert channel['installation']['observation_seconds']>=120
        for row in rows:
            path=(ROOT/row['source']).resolve();assert path.is_relative_to((ARCHIVE/'source').resolve())
            raw=path.read_bytes();assert len(raw)==row['size']
            assert hashlib.sha256(raw).hexdigest()==row['sha256']
            ast.parse(raw);assert not guard.find(raw.decode('utf8')),row['source']
            unique.add(row['source']);count+=1
    assert count==10 and len(unique)==6
    subprocess.run([sys.executable,'-B',str(ARCHIVE/'validation/check_spatial_error_codes.py'),'--self-test'],check=True,cwd=ROOT)
    subprocess.run([sys.executable,'-B',str(ARCHIVE/'validation/test_entry_failure_payload.py')],check=True,cwd=ROOT)
    print(json.dumps(dict(ok=True,exact_channel_sources=count,unique_sources=len(unique),runtime_executed=False,natural_GUI=False)))

if __name__=='__main__':main()
