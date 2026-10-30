"""Compose the bounded room marker adapter into existing owned cache startup."""
from pathlib import Path
import hashlib,json

EXE_SHA='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
IMAGE_SHA='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'


def compose(snapshot,executable_sha256,template):
    if executable_sha256!=EXE_SHA or hashlib.sha256(snapshot).hexdigest()!=IMAGE_SHA:
        raise ValueError('Dungeon map client identity')
    anchor=" for(const [r,h]of Object.entries(pins))if(bytes(module.base.add(+r))!==h)throw Error('Native power sync identity '+r);"
    if template.count(anchor)!=1:
        raise ValueError('Dungeon map startup composition anchor')
    raw=Path(__file__).with_suffix('.js').read_text('utf-8')
    if raw.count('__DUNGEON_MAP_PINS__')!=1:
        raise ValueError('Dungeon map source contract')
    sizes={0x1070c20:32,0x10710cd:13,0x3554020:16,0x3556210:16,0x4ab640:16,0x4ab6d0:16,0x104df40:27}
    pins={r:snapshot[r:r+n].hex()for r,n in sizes.items()}
    raw=raw.replace('__DUNGEON_MAP_PINS__',json.dumps(pins))
    return raw+'\n'+template.replace(anchor,anchor+'\n installElsDungeonMapMarkers();')
