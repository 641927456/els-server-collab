"""Immutable current-build rules for the qualified scalar attribute phases."""
import functools
import hashlib
import json
from types import MappingProxyType
from els_server.paths import PROJECT_ROOT

RULES_SHA256 = '1d8a5dd2b0e0c9f84da74f4b6b807eb6cbe0287b25b2ddf43396e475c9c862d4'
IMAGE_SHA256 = 'c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'


def _freeze(value):
    if type(value) is dict:
        return MappingProxyType({key:_freeze(item) for key,item in value.items()})
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


def decode(raw):
    if type(raw) is not bytes or hashlib.sha256(raw).hexdigest()!=RULES_SHA256:
        raise ValueError('Native attribute rule identity changed')
    source=json.loads(raw)
    if (source.get('schema')!=1 or source.get('image_sha256')!=IMAGE_SHA256
            or source.get('original_function')!='8978C0'):
        raise ValueError('Native attribute source version changed')
    rows=source['rules']
    if len(rows)!=72 or sum(len(row['operations'])for row in rows)!=83:
        raise ValueError('Native scalar phase coverage changed')
    return _freeze(rows)


@functools.lru_cache(maxsize=1)
def rules():
    path=PROJECT_ROOT/'els_server/data/native_attributes/passive-stat-rules.json'
    return decode(path.read_bytes())
