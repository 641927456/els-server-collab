"""Validate a first-install marker before the existing local server creates a new save."""
from pathlib import Path
import hashlib
import json


def _regular_path(path, root):
    path, root = Path(path).absolute(), Path(root).absolute()
    if not path.is_relative_to(root):
        raise ValueError('Fresh local path escaped workspace')
    for part in (path, *path.parents):
        if part.exists() or part.is_symlink():
            if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
                raise ValueError('Fresh local path contains a link')
        if part == root:
            break


def fresh_local_allowed(root, config_path, save):
    """False preserves legacy startup; a malformed present marker never bypasses checks."""
    root, config_path, save = Path(root).absolute(), Path(config_path).absolute(), Path(save).absolute()
    marker_path = root / 'local-first-run.json'
    if not marker_path.exists() and not marker_path.is_symlink():
        return False
    _regular_path(marker_path, root)
    if marker_path.stat().st_size > 16384:
        raise ValueError('Fresh local marker is too large')
    doc = json.loads(marker_path.read_bytes())
    if set(doc) != {'schema', 'kind', 'workspace', 'release', 'state_file', 'config_sha256'}:
        raise ValueError('Invalid fresh local marker schema')
    if doc['schema'] != 1 or doc['kind'] != 'els-local-fresh-state':
        raise ValueError('Invalid fresh local marker kind')
    workspace = Path(doc['workspace'])
    if not workspace.is_absolute() or workspace != workspace.resolve():
        raise ValueError('Invalid fresh local workspace')
    if (not isinstance(doc['release'], str) or not doc['release'] or
            any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in doc['release'])):
        raise ValueError('Invalid fresh local release')
    if root != workspace / 'releases' / 'local' / doc['release']:
        raise ValueError('Fresh local release root differs')
    if config_path != root / 'config' / 'server.toml' or save != workspace / 'state' / 'integrated.sqlite3':
        raise ValueError('Fresh local config or save differs')
    if doc['state_file'] != str(save):
        raise ValueError('Fresh local saved path differs')
    _regular_path(root, workspace)
    _regular_path(marker_path, workspace)
    _regular_path(config_path, workspace)
    _regular_path(save, workspace)
    if hashlib.sha256(config_path.read_bytes()).hexdigest() != doc['config_sha256']:
        raise ValueError('Fresh local config changed')
    # This grants only creation through the ordinary server, never replacement/import.
    if save.exists():
        return False
    return True
