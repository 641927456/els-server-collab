"""Compose the two pinned CX2World post-destruction iterator repairs."""
from pathlib import Path
import hashlib,json
EXE_SHA='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
BODY_SHA='f49599d45d4196e413d104fc48895020703dd8f643fb65b0ef29aa5c06ea84f8'
def compose(snapshot,executable_sha256,template):
    if executable_sha256!=EXE_SHA or hashlib.sha256(snapshot[0x92e010:0x92e636]).hexdigest()!=BODY_SHA:
        raise ValueError('World event method identity')
    anchor=" for(const [r,h]of Object.entries(pins))if(bytes(module.base.add(+r))!==h)throw Error('Native power sync identity '+r);"
    if template.count(anchor)!=1:raise ValueError('World event startup anchor')
    sizes={0x92e010:32,0x91ea1c:5,0x92e09e:5,0x92e0a3:64,0x92e0c8:16,0x92e0d8:18,0x92e13c:19,0x92e1bb:5,0x92e1c0:64,0x92e1e5:16,0x92e1f5:18,0x92e25c:19,0x923ff0:32}
    raw=Path(__file__).with_suffix('.js').read_text('utf8')
    if raw.count('__WORLD_EVENT_PINS__')!=1:raise ValueError('World event source anchor')
    raw=raw.replace('__WORLD_EVENT_PINS__',json.dumps({r:snapshot[r:r+n].hex()for r,n in sizes.items()}))
    return raw+'\n'+template.replace(anchor,anchor+'\n installElsWorldEventIteration();')
