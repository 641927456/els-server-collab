"""Check the accepted source archive, optionally against a local update checkout."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'references/accepted-runtime-20261026-v1'


def safe(name):
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or ':' in name or '\\' in name:
        raise ValueError('Unsafe archive path')
    return p


def verify(local_source_root=None):
    manifest = json.loads((ARCHIVE / 'manifest.json').read_bytes())
    assert manifest['schema'] == 1 and manifest['gameplay_changes'] == 0
    assert not manifest['accounts_or_saves_included'] and not manifest['runtime_binaries_included']
    seen = set()
    result = {}
    effective = {}
    for channel, description in manifest['channels'].items():
        assert channel in ('local', 'online') and description['accepted_observation_seconds'] >= 120
        rows = description['source_files']
        assert len(rows) == description['source_count'] == len({r['path'] for r in rows})
        compiled = 0
        effective[channel] = {}
        for row in rows:
            rel = safe(row['path'])
            location = safe(row['archive'])
            assert str(location) in ('shared/' + str(rel), channel + '/' + str(rel))
            path = ARCHIVE / location
            assert not path.is_symlink() and path.resolve().is_relative_to(ARCHIVE.resolve())
            raw = path.read_bytes()
            assert len(raw) == row['size'] and hashlib.sha256(raw).hexdigest() == row['sha256']
            if rel.suffix == '.py':
                compile(raw, str(location), 'exec')
                compiled += 1
            elif rel.suffix == '.json':
                json.loads(raw)
            else:
                raise ValueError('Unexpected source extension')
            effective[channel][str(rel)] = dict(size=len(raw), sha256=row['sha256'])
            seen.add(str(location))
        assert compiled == description['python_count']
        result[channel] = dict(source_files=len(rows), python_compiled=compiled)
    actual = {p.relative_to(ARCHIVE).as_posix() for p in ARCHIVE.rglob('*') if p.is_file()}
    assert actual == seen | {'manifest.json'}
    assert len(seen) == manifest['physical_source_files']
    successor_root = ROOT / 'references/accepted-runtime-20261026-v2'
    successor_file = successor_root / 'manifest.json'
    successor_count = 0
    if successor_file.is_file():
        successor = json.loads(successor_file.read_bytes())
        assert successor['schema'] == 1 and successor['kind'] == 'exact-accepted-source-successor'
        assert successor['base_manifest'] == ARCHIVE.relative_to(ROOT).as_posix() + '/manifest.json'
        assert successor['base_manifest_sha256'] == hashlib.sha256((ARCHIVE / 'manifest.json').read_bytes()).hexdigest()
        assert successor['gameplay_changes'] == 0 and not successor['deployment_performed']
        assert not successor['private_state_included'] and not successor['client_files_included']
        assert set(successor['channels']) == set(effective)
        successor_seen = set()
        for channel, description in successor['channels'].items():
            assert description['accepted_observation_seconds'] >= 120
            assert description['source_count'] == len(effective[channel])
            changed = set()
            for row in description['overrides']:
                rel = safe(row['path'])
                location = safe(row['archive'])
                assert str(location) == 'shared/' + str(rel)
                assert str(rel) not in changed and str(rel) in effective[channel]
                assert effective[channel][str(rel)]['sha256'] == row['before_sha256']
                path = successor_root / location
                assert not path.is_symlink() and path.resolve().is_relative_to(successor_root.resolve())
                raw = path.read_bytes()
                assert len(raw) == row['size'] and hashlib.sha256(raw).hexdigest() == row['sha256']
                if rel.suffix == '.py':
                    compile(raw, str(location), 'exec')
                elif rel.suffix == '.json':
                    json.loads(raw)
                else:
                    raise ValueError('Unexpected successor source extension')
                effective[channel][str(rel)] = dict(size=len(raw), sha256=row['sha256'])
                changed.add(str(rel))
                successor_seen.add(str(location))
            values = sorted((name, row['size'], row['sha256']) for name, row in effective[channel].items())
            digest = hashlib.sha256(json.dumps(values, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
            assert digest == description['effective_source_digest']
            result[channel]['release'] = description['release']
            result[channel]['successor_sources'] = len(changed)
        actual = {p.relative_to(successor_root).as_posix() for p in successor_root.rglob('*') if p.is_file()}
        assert actual == successor_seen | {'manifest.json'}
        assert len(successor_seen) == successor['physical_source_files']
        successor_count = len(successor_seen)
    if local_source_root is not None:
        for name, row in effective['local'].items():
            raw = (local_source_root / safe(name)).read_bytes()
            assert len(raw) == row['size'] and hashlib.sha256(raw).hexdigest() == row['sha256'], name
    return dict(ok=True, channels=result, distinct_source_files=len(seen),
                successor_source_files=successor_count,
                current_local_checkout_verified=local_source_root is not None,
                server_or_database_actions=0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--local-source-root', type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.local_source_root)))
