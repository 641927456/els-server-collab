"""Check immutable paired TradeBoard source references without runtime assets."""
from pathlib import Path
import ast,hashlib,json

ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=ROOT/'references/f-trade-board-native-20261026-v1'

def verify():
    manifest=json.loads((ARCHIVE/'manifest.json').read_bytes())
    assert manifest['issue']==537 and manifest['client_delta']==0
    assert not manifest['formal_installed']
    assert len(manifest['files'])==28 and len(manifest['source_paths'])==25
    assert len(set(manifest['source_paths']))==25
    for channel in ('online','local'):
        rows=[r for r in manifest['files']if channel in r['channels']]
        assert {r['source_path']for r in rows}==set(manifest['source_paths'])
        assert len(rows)==25
    actual={p.relative_to(ARCHIVE).as_posix()for d in ('shared','online','local')for p in (ARCHIVE/d).rglob('*')if p.is_file()}
    assert actual=={r['path']for r in manifest['files']}
    for row in manifest['files']:
        p=(ARCHIVE/row['path']).resolve()
        assert p.is_relative_to(ARCHIVE.resolve())
        raw=p.read_bytes()
        assert hashlib.sha256(raw).hexdigest()==row['sha256'],row['path']
        if p.suffix=='.py':ast.parse(raw)
    edits=json.loads((ARCHIVE/'patch-contract.json').read_bytes())['shared_edits']
    assert len(edits)==6
    for edit in edits:
        assert edit['inverse_patch_exact_parent_bytes']
        row=next(r for r in manifest['files']if r['source_path']==edit['path']and edit['channel']in r['channels'])
        assert row['sha256']==edit['after_sha256']
        assert len(edit['parent_sha256'])==64
        assert edit['patch'].startswith('--- before/')
        # Two insertion hooks and one exact receipt-kind tuple extension.
        changes=edit['patch'].splitlines()[2:]
        removed=[line[1:]for line in changes if line.startswith('-')]
        added=[line[1:]for line in changes if line.startswith('+')]
        if edit['path']=='els_server/storage/equipment_receipt_state.py':
            assert len(removed)==len(added)==1
            assert removed[0].count('0xd54,0xd56):')==1
            assert added[0]==removed[0].replace('0xd54,0xd56):','0xd54,0xd56,0xa08,0xa04,0xa06,0x9fc):')
        else:assert not removed
    qualified=json.loads((ARCHIVE/'qualified-summary.json').read_bytes())
    assert not qualified['formal_installed'] and not qualified['natural_GUI']
    assert len(qualified['dual_private_application'])==2
    for result in qualified['dual_private_application']:
        assert result['ok']and result['checks']==15 and result['private_store_removed']
        assert result['production_actions']==0
    assert len(qualified['non_F_native_refusal'])==2
    for result in qualified['non_F_native_refusal']:
        assert result['ok']and result['checks']==4 and result['private_store_removed']
        assert result['production_actions']==0
    return dict(ok=True,channel_leaves=25,archived_source_files=28,minimal_shared_hooks=6,production_actions=0)

if __name__=='__main__':print(json.dumps(verify()))
