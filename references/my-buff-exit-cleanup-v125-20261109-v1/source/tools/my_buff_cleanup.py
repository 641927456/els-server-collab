"""Compose the pinned MyBuff erased-node iterator repair at the owned startup callback."""
from pathlib import Path
import hashlib
import json
import struct

EXE_SHA = '6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
IMAGE_SHA = 'c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
CLEANUP = (0x3586460, 0x35865A5, 'e40548ed9c5f0f32a30c3007336a159319f47bac0c4fb3fee07f14be15fae9ef')
REMOVE = (0x3586C00, 0x3586C6F, '7ac964e30375abdf9ece27ad640d25e56b54c9cf192d73aa1a1a575415a0cd69')
VTABLE = 0x4334648
SITE = 0x358653F
RESUME = 0x358658F
OVERWRITE_SIZE = 18
REDIRECT_PADDING = '660f1f8400000000000f1f4000'
ANCHOR = " for(const [r,h]of Object.entries(pins))if(bytes(module.base.add(+r))!==h)throw Error('Native power sync identity '+r);"


def compose(snapshot, executable_sha256, template):
    if executable_sha256 != EXE_SHA or hashlib.sha256(snapshot).hexdigest() != IMAGE_SHA:
        raise ValueError('MyBuff client/image identity')
    bodies = {}
    for start, end, expected in (CLEANUP, REMOVE):
        body = snapshot[start:end]
        if hashlib.sha256(body).hexdigest() != expected:
            raise ValueError('MyBuff native method identity')
        bodies[start] = body.hex()
    if struct.unpack_from('<Q', snapshot, VTABLE + 0x1E0)[0] != 0x140000000 + REMOVE[0]:
        raise ValueError('MyBuff native virtual identity')
    if template.count(ANCHOR) != 1:
        raise ValueError('MyBuff startup anchor')
    raw = Path(__file__).with_suffix('.js').read_text(encoding='utf8')
    if raw.count('__MY_BUFF_CLEANUP_PROFILE__') != 1:
        raise ValueError('MyBuff source anchor')
    profile = dict(cleanup=CLEANUP[0], remove=REMOVE[0], vtable=VTABLE, site=SITE,
                   resume=RESUME, overwrite_size=OVERWRITE_SIZE,
                   redirect_padding=REDIRECT_PADDING, bodies=bodies,
                   executable_sha256=EXE_SHA, image_sha256=IMAGE_SHA)
    raw = raw.replace('__MY_BUFF_CLEANUP_PROFILE__', json.dumps(profile, separators=(',', ':')))
    return raw + '\n' + template.replace(ANCHOR, ANCHOR + '\n installElsMyBuffCleanupOnce();')
