"""Verify the source-only qualified archive without launching private QA."""
from pathlib import Path
import hashlib,json

ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=ROOT/'references/background-native-gear-20261026-v1'

def main():
    read=lambda p:json.loads(p.read_text('utf8'))
    manifest=read(ARCHIVE/'manifest.json');qualified=read(ARCHIVE/'qualification.json');dual=read(ARCHIVE/'dual-installation.json')
    assert manifest['schema_version']==1 and manifest['issue']==535
    assert manifest['source_archive_does_not_deploy'] and not any(manifest['forbidden_exports'].values())
    rows=manifest['source_files'];assert len(rows)==10 and len({r['path']for r in rows})==len(rows)
    assert {p.relative_to(ARCHIVE).as_posix()for p in (ARCHIVE/'sources').rglob('*')if p.is_file()}=={r['path']for r in rows}
    for row in rows:
        rel=Path(row['path']);assert not rel.is_absolute()and '..'not in rel.parts and rel.parts[0]=='sources'
        p=ARCHIVE/rel;raw=p.read_bytes();assert p.suffix in('.py','.js')and len(raw)==row['size']
        assert hashlib.sha256(raw).hexdigest()==row['sha256']
        assert row['qualified_source_bytes_unchanged']and qualified['source_files'][row['source_workspace_path']]==row['sha256']
    assert qualified['passed']and qualified['complete_native_actions']==16 and qualified['cold_client_verified']
    assert qualified['physical_input_actions']==0 and not qualified['production_database_access']
    assert qualified['controlled_native_callbacks']and not qualified['natural_mouse_clicks_tested']
    assert qualified['client_copies']==0 and not qualified['original_client_modified']
    assert all(qualified['cleanup'].values())
    assert dual['ok']and dual['read_only']and dual['production_DB_writes']==0
    assert dual['server_fix_PRs']==[512,513]and dual['remote']['healthy']
    assert dual['remote']['manifest_sha256']==dual['channels']['online']['manifest_sha256']
    for channel in dual['channels'].values():assert len(channel['gear_fix_checks'])==10
    print(json.dumps(dict(ok=True,source_files=len(rows),native_actions=16,cold_client=True,no_client_launch=True)))

if __name__=='__main__':main()
