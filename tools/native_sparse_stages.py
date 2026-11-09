"""Use the original parser for the pinned source's second, non-contiguous stage."""
from pathlib import Path
import hashlib,json
EXE_SHA='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
IMAGE_SHA='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
SOURCE_SHA='3b7feb6b68743dc3bd7f77f03a792a5c9e87a08803dcc84f63d9c421693a345f'
def compose(snapshot,executable_sha256,template):
    if executable_sha256!=EXE_SHA or hashlib.sha256(snapshot).hexdigest()!=IMAGE_SHA:
        raise ValueError('Sparse stage client identity')
    anchor=" for(const [r,h]of Object.entries(pins))if(bytes(module.base.add(+r))!==h)throw Error('Native power sync identity '+r);"
    if template.count(anchor)!=1:raise ValueError('Sparse stage startup anchor')
    raw=Path(__file__).with_suffix('.js').read_text('utf8')
    if raw.count('__SPARSE_STAGE_PINS__')!=1:raise ValueError('Sparse stage source contract')
    sizes={0x1034ba0:32,0x1036036:19,0x10360eb:42,0x393a010:32,0x10347c0:32}
    pins={r:snapshot[r:r+n].hex()for r,n in sizes.items()}
    # Use the existing verified-code startup, before any dungeon resource load.
    # The first owned Game/cache callback is later than the stage parser.
    early="  clearInterval(timer);\n  installElsWearSync();"
    if template.count(early)!=1:raise ValueError('Sparse stage verified startup anchor')
    return raw.replace('__SPARSE_STAGE_PINS__',json.dumps(pins))+'\n'+template.replace(early,early+'\n  installElsSparseStages();')
