"""Load build-generated, digest-bound native support; no server catalog import."""
import functools
import hashlib
import json
from pathlib import Path

EXE_SHA = '6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
IMAGE_SHA = 'c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
SUPPORT_SHA = '012308ec6877d8d4f9423602da119fa0f02484f1c8d2ecd7789bffc1a988661c'

@functools.lru_cache(maxsize=1)
def load():
    raw=Path(__file__).with_suffix('.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SUPPORT_SHA:
        raise ValueError('Native support identity changed; use normal launcher update')
    data=json.loads(raw)
    if data['schema']!=1 or data['executable_sha256']!=EXE_SHA or data['source_image_sha256']!=IMAGE_SHA:
        raise ValueError('Native support client contract')
    return data

def script(name):
    return load()['scripts'][name]

def prefix(rva, size=8):
    return load()['prefixes'+str(size)][str(rva)]
