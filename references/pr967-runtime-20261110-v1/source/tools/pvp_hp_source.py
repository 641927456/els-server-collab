"""Add the minimum native maximum-HP report support at existing startup."""
from pathlib import Path
import hashlib,json
EXE_SHA='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
IMAGE_SHA='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
def compose(snapshot,executable_sha256,template):
    if executable_sha256!=EXE_SHA or hashlib.sha256(snapshot).hexdigest()!=IMAGE_SHA:raise ValueError('PvP native support client identity')
    anchor=" for(const [r,h]of Object.entries(pins))if(bytes(module.base.add(+r))!==h)throw Error('Native power sync identity '+r);"
    if template.count(anchor)!=1:raise ValueError('PvP native support startup anchor')
    # Vtable pointers relocate with ASLR; verify its address at capture time,
    # never compare its relocated contents with the recorded process bytes.
    sizes={0x1ab7ac0:16,0xda2f50:16,0xc69094:13,0x8571d0:16,0x7d57a0:16,0x7d8b00:16,0x3b6dbd0:16,0x3b6dcc0:16}
    script=Path(__file__).with_suffix('.js').read_text(encoding='utf8')
    if script.count('__PVP_HP_PINS__')!=1:raise ValueError('PvP native source pin anchor')
    script=script.replace('__PVP_HP_PINS__',json.dumps({r:snapshot[r:r+n].hex()for r,n in sizes.items()}))
    return script+'\n'+template.replace(anchor,anchor+'\n installElsPvpHpSource();')
