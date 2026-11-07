"""Prepare the process-lifetime native send lock, with immutable client pins.

This candidate is deliberately not wired into the production launcher before
independent review and owned game lifecycle qualification.
"""
from pathlib import Path
import hashlib,json

EXE_SHA='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
IMAGE_SHA='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'

def source(snapshot,executable_sha256):
    if executable_sha256!=EXE_SHA or hashlib.sha256(snapshot).hexdigest()!=IMAGE_SHA:
        raise ValueError('Native send serialization client identity')
    # Existing trace/CP observers own the entry; use untouched body anchors.
    anchors={0x682da0:16,0x683104:5,0x68318c:5,0x3b7d860:16,
             0x1271e60:4,0x3b817b0:4,0x6875a0:16}
    raw=Path(__file__).with_suffix('.js').read_text('utf8')
    if raw.count('__SEND_SERIALIZATION_PINS__')!=1:
        raise ValueError('Native send serialization source anchor')
    return raw.replace('__SEND_SERIALIZATION_PINS__',json.dumps({r:snapshot[r:r+n].hex()for r,n in anchors.items()}))
