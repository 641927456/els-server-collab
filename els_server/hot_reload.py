"""Local-only hot reload for business modules that are imported lazily.

The local profile runs in one process next to the game. Reworking a handler
normally means stopping the server, which drops the client connection. This
watcher re-executes a short whitelist of stateless modules in place so the next
request already uses the edited code and the game keeps its session.

Safety rules kept deliberately narrow:

* Only modules that are imported inside functions may be listed. Reloading a
  module whose classes are held by live sessions would break isinstance checks.
* Reload order follows the list, dependencies first.
* Nothing here touches the client, sockets, saves or the protocol.
* Enabled by default for ``mode = "local"`` only; set ``ELS_HOT_RELOAD=0`` to
  switch it off, or ``ELS_HOT_RELOAD=1`` to force it on.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import threading
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUEST_FILE = ROOT / 'state/hot-reload.request'
CONFIG_FILE = ROOT / 'state/hot-reload.json'

# Imported by session_dispatch/handlers inside function bodies, never hoisted
# to module level by anything holding live state.
DEFAULT_MODULES = (
    'els_server.protocol.bag_expansion_messages',
    'els_server.domain.bag_expansion_flow',
    'els_server.domain.bag_capacity',
    'els_server.storage.bag_capacity',
    'els_server.domain.session_dispatch',
)

POLL_SECONDS = 0.5
_lock = threading.Lock()


def enabled(config=None) -> bool:
    value = os.environ.get('ELS_HOT_RELOAD')
    if value is not None:
        return value.strip().lower() not in ('0', 'false', 'no', 'off', '')
    return getattr(config, 'mode', None) == 'local'


def modules() -> tuple[str, ...]:
    """Whitelist from state/hot-reload.json, falling back to the default set.

    The file may only narrow this list, never extend it: a module name it
    invents is ignored, so writing state/ cannot turn into code execution.
    """
    try:
        rows = json.loads(CONFIG_FILE.read_text(encoding='utf8'))
    except (OSError, ValueError):
        return DEFAULT_MODULES
    names = rows.get('modules') if isinstance(rows, dict) else rows
    if not isinstance(names, list) or not names:
        return DEFAULT_MODULES
    selected = {name for name in names if isinstance(name, str)}
    return tuple(name for name in DEFAULT_MODULES if name in selected)


def _source_stamp(module) -> tuple | None:
    path = getattr(module, '__file__', None)
    if not path:
        return None
    try:
        info = Path(path).stat()
    except OSError:
        return None
    return (info.st_mtime_ns, info.st_size)


def stamps(names) -> dict:
    result = {}
    for name in names:
        module = sys.modules.get(name)
        if module is not None:
            result[name] = _source_stamp(module)
    return result


def reload_modules(names) -> list[str]:
    """Re-execute the named modules in place; return the ones that changed.

    Raises nothing: a broken edit must leave the old module usable, so failures
    are reported back to the caller instead of escaping into the request path.
    """
    with _lock:
        reloaded = []
        for name in names:
            module = sys.modules.get(name)
            if module is None:
                continue
            try:
                importlib.reload(module)
                reloaded.append(name)
            except Exception:
                traceback.print_exc()
        return reloaded


def _write(log_path: Path | None, line: str) -> None:
    text = time.strftime('%Y-%m-%dT%H:%M:%S ') + line
    print('ELS_HOT_RELOAD: ' + line, flush=True)
    if log_path is None:
        return
    try:
        with log_path.open('a', encoding='utf8') as stream:
            stream.write(text + '\n')
    except OSError:
        pass


def watch(log_dir=None, names=None, poll=POLL_SECONDS) -> None:
    """Poll source mtimes; reload on change or on an explicit request file."""
    names = tuple(names or modules())
    log_path = Path(log_dir) / 'hot-reload.log' if log_dir else None
    _write(log_path, 'watching ' + ', '.join(names))
    seen = stamps(names)
    while True:
        time.sleep(poll)
        forced = REQUEST_FILE.exists()
        current = stamps(names)
        # A module imported after startup has no previous stamp; record it
        # without reloading so the first sighting is never treated as an edit.
        changed = [name for name, stamp in current.items()
                   if name in seen and seen[name] != stamp]
        if forced and not changed:
            changed = [name for name in names if name in current]
        if not changed:
            continue
        targets = [name for name in names if name in changed]
        try:
            reloaded = reload_modules(targets)
            _write(log_path, ('forced ' if forced else 'changed ') + ', '.join(reloaded or targets))
        finally:
            seen = stamps(names)
            if forced:
                try:
                    REQUEST_FILE.unlink()
                except OSError:
                    pass


def start(config, names=None) -> threading.Thread | None:
    if not enabled(config):
        return None
    if getattr(sys, 'frozen', False):
        return None
    thread = threading.Thread(target=watch, kwargs=dict(log_dir=getattr(config, 'log_dir', None), names=names),
                              name='els-hot-reload', daemon=True)
    thread.start()
    return thread
