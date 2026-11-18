"""GM policy for the native STR_ID_350 safety notice, separate per deployment."""
import functools
import hashlib
import json
import os
from pathlib import Path
import tempfile

_path = None


def configure(path):
    global _path
    _path = Path(path)
    _load.cache_clear()


def validate(value):
    if not isinstance(value, dict) or set(value) != {'enabled', 'text'}:
        raise ValueError('客户端提示字段无效')
    text = value['text']
    if type(value['enabled']) is not bool or not isinstance(text, str):
        raise ValueError('客户端提示开关或正文无效')
    if (not text.strip() or len(text.encode('utf-16le')) > 560
            or any(ord(c) < 32 and c != '\n' or ord(c) == 127 for c in text)
            or any(c in text for c in '<>') or '#c' in text.casefold()):
        raise ValueError('提示正文须为 1—280 字纯文本，可换行，不接受颜色标记')
    return dict(enabled=value['enabled'], text=text)


def defaults():
    return json.loads((Path(__file__).resolve().parents[1] / 'data/client_notices.json').read_bytes())


@functools.lru_cache(maxsize=1)
def _load():
    return validate(json.loads(_path.read_bytes()) if _path is not None and _path.exists() else defaults())


def policy():
    value = _load()
    revision = hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return dict(value, revision=revision)


def snapshot():
    return dict(policy(), original_text=defaults()['text'], text_id=350,
                interval_seconds=3600, sync_seconds=30)


def update(settings, expected_revision):
    value = validate(settings)
    if _path is None:
        raise ValueError('客户端提示配置尚未初始化')
    if policy()['revision'] != expected_revision:
        raise ValueError('客户端提示已被更新，请重新载入后再保存')
    _path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf8', newline='\n',
                                         dir=_path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(_path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    _load.cache_clear()
    return snapshot()
