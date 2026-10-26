"""Rebuild a pinned engine without replacing a checkout or reading live saves."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import os
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / 'channels/formal-clock-20261027-v1.json'


def relative(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value:
        raise ValueError('Invalid relative path')
    path = PurePosixPath(value)
    if path.is_absolute() or str(path) != value or any(p in ('', '.', '..') or p.rstrip(' .') != p for p in path.parts):
        raise ValueError('Non-canonical relative path')
    reserved = {'con', 'prn', 'aux', 'nul'} | {f'{p}{i}' for p in ('com', 'lpt') for i in range(1, 10)}
    if any(p.split('.')[0].casefold() in reserved for p in path.parts):
        raise ValueError('Reserved path')
    return path


def bound(root, value):
    relative(value)
    result = (root / value).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError('Source escapes its root')
    return result


def verify(path, entry):
    if not path.is_file() or path.stat().st_size != entry['size']:
        raise ValueError(f"Missing or wrong size: {entry['path']}")
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != entry['sha256']:
        raise ValueError(f"Hash mismatch: {entry['path']}")


def plan(repo, manifest, channel, assets_root=None):
    rows = manifest['channels'][channel]['files']
    locked = {r['path']: r for r in json.loads((repo / 'runtime-assets.lock.json').read_bytes())['files']}
    seen = set()
    result = []
    for entry in rows:
        path = str(relative(entry['path']))
        if path.casefold() in seen:
            raise ValueError('Duplicate output path')
        seen.add(path.casefold())
        if ('source' in entry) == ('asset' in entry):
            raise ValueError('Exactly one source is required')
        if 'asset' in entry:
            if entry['asset'] != path or path not in locked or any(entry[k] != locked[path][k] for k in ('sha256', 'size')):
                raise ValueError('Resource is not in the existing lock')
            source = bound(assets_root, path) if assets_root is not None else None
        else:
            source = bound(repo, entry['source'])
        if source is not None:
            verify(source, entry)
        result.append((entry, source))
    return result


def materialize(repo, manifest, channel, output, *, assets_root=None, link_assets=False):
    repo, output = Path(repo).resolve(), Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError('Output already exists; in-place replacement is forbidden')
    if not output.parent.is_dir():
        raise ValueError('Output parent must exist')
    if link_assets and assets_root is None:
        raise ValueError('Asset root required')
    rows = plan(repo, manifest, channel, Path(assets_root).resolve() if assets_root else None)
    staging = Path(tempfile.mkdtemp(prefix=output.name + '.building-', dir=output.parent)).resolve()
    assert staging.parent == output.parent.resolve()
    try:
        for entry, source in rows:
            if source is None:
                continue
            target = staging / entry['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            if link_assets and 'asset' in entry:
                os.link(source, target)
            else:
                shutil.copyfile(source, target)
            verify(target, entry)
        receipt = {'channel': channel, 'release': manifest['channels'][channel]['release'],
                   'source_files': sum('source' in e for e, _ in rows),
                   'asset_files': sum('asset' in e for e, _ in rows),
                   'assets_materialized': assets_root is not None,
                   'asset_links': link_assets, 'files': [e for e, _ in rows]}
        (staging / 'engine-source-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf8')
        if output.exists():
            raise ValueError('Output appeared during validation')
        staging.rename(output)
        return {k: v for k, v in receipt.items() if k != 'files'}
    finally:
        if staging.exists():
            # Only this invocation's newly created, verified sibling tree.
            assert staging.parent == output.parent.resolve() and staging.name.startswith(output.name + '.building-')
            shutil.rmtree(staging)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=DEFAULT)
    parser.add_argument('--channel', choices=('online', 'local'), required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--assets-root', type=Path, help='Already bootstrapped locked static assets; no player data')
    parser.add_argument('--link-assets', action='store_true', help='Same-volume disposable QA view; do not edit linked resources')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_bytes())
    if args.verify_only:
        rows = plan(ROOT, manifest, args.channel, args.assets_root)
        print(json.dumps({'ok': True, 'verified_sources': sum(s is not None for _, s in rows),
                          'unmaterialized_locked_assets': sum(s is None for _, s in rows)}))
    else:
        if args.output is None:
            parser.error('--output is required')
        print(json.dumps(materialize(ROOT, manifest, args.channel, args.output,
                                     assets_root=args.assets_root, link_assets=args.link_assets)))


if __name__ == '__main__':
    main()
