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
    for channel, description in manifest['channels'].items():
        assert channel in ('local', 'online') and description['accepted_observation_seconds'] >= 120
        rows = description['source_files']
        assert len(rows) == description['source_count'] == len({r['path'] for r in rows})
        compiled = 0
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
            if channel == 'local' and local_source_root is not None:
                assert (local_source_root / rel).read_bytes() == raw, str(rel)
            seen.add(str(location))
        assert compiled == description['python_count']
        result[channel] = dict(source_files=len(rows), python_compiled=compiled)
    actual = {p.relative_to(ARCHIVE).as_posix() for p in ARCHIVE.rglob('*') if p.is_file()}
    assert actual == seen | {'manifest.json'}
    assert len(seen) == manifest['physical_source_files']
    return dict(ok=True, channels=result, distinct_source_files=len(seen),
                current_local_checkout_verified=local_source_root is not None,
                server_or_database_actions=0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--local-source-root', type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.local_source_root)))
