"""Verify the delivered seven-file archive, without executing private fixtures."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'refs/online-long-pauses-20261103-v1'


def main():
    contract = json.loads((ARCHIVE / 'source-contract.json').read_bytes())
    assert contract['reference_only'] and len(contract['files']) == 7
    assert len({row['runtime_path'] for row in contract['files']}) == 7
    assert contract['new_tables'] == [] and len(contract['new_indexes']) == 3
    patch = []
    for row in contract['files']:
        path = row['runtime_path']
        for side in ('parent', 'source'):
            entry = row[side]
            assert entry['path'] == side + '/' + path
            raw = (ARCHIVE / entry['path']).read_bytes()
            assert len(raw) == entry['size']
            assert hashlib.sha256(raw).hexdigest() == entry['sha256'], path
            ast.parse(raw, filename=entry['path'])
        patch.extend(difflib.unified_diff(
            (ARCHIVE / row['parent']['path']).read_text('utf8').splitlines(True),
            (ARCHIVE / row['source']['path']).read_text('utf8').splitlines(True),
            fromfile='a/' + path, tofile='b/' + path))
    assert (ARCHIVE / 'source.patch').read_text('utf8') == ''.join(patch)
    for name, entry in contract['artifacts'].items():
        path = ARCHIVE / name
        assert path.resolve().is_relative_to(ARCHIVE.resolve())
        raw = path.read_bytes()
        assert len(raw) == entry['size']
        assert hashlib.sha256(raw).hexdigest() == entry['sha256'], name
        if path.suffix == '.py':
            ast.parse(raw, filename=name)
    for name in ('facts-benchmark', 'task-cursors', 'clock-tracing',
                 'projection-reuse', 'actual-parent-runtime'):
        assert json.loads((ARCHIVE / 'results' / (name + '.json')).read_bytes())['passed']
    delivery = json.loads((ARCHIVE / 'actual-delivery-summary.json').read_bytes())
    for result in delivery.values():
        assert result['online_installed'] and result['observation_seconds'] >= 120
        assert result['own_QA_cleaned'] and result['publication_closed']
        assert not result['player_database_restore']
    assert delivery['v4']['natural_requests'] == 0
    print(json.dumps(dict(ok=True, runtime_files=7, source_objects=14,
                          artifacts=len(contract['artifacts']),
                          private_business_tests_rerun=False)))


if __name__ == '__main__':
    main()
