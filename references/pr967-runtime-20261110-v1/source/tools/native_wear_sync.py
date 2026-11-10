"""Pinned native104/105 wait guard for the shared startup support script."""
import hashlib
import json
from pathlib import Path

EXE_SHA='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
IMAGE_SHA='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'


def source(snapshot, executable_sha256):
    if executable_sha256!=EXE_SHA or hashlib.sha256(snapshot).hexdigest()!=IMAGE_SHA:
        raise ValueError('Native wear synchronization client identity')
    script=Path(__file__).with_suffix('.js').read_text(encoding='utf8')
    if script.count('__WEAR_SYNC_PINS__')!=1:
        raise ValueError('Native wear synchronization source contract')
    pins={0x22634a0:snapshot[0x22634a0:0x22634b5].hex(),
          0x74fa90:snapshot[0x74fa90:0x74face].hex()}
    return script.replace('__WEAR_SYNC_PINS__',json.dumps(pins))
