"""Append native CP at the existing owned event encoder, preserving original fields."""
from pathlib import Path
import hashlib,json
EXE_SHA='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
IMAGE_SHA='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'

def source(snapshot,executable_sha256):
    if executable_sha256!=EXE_SHA or hashlib.sha256(snapshot).hexdigest()!=IMAGE_SHA:raise ValueError('Raid native CP client identity')
    # Existing signed trace/group-wear observers already own entry trampolines.
    # Bind untouched bodies in the same functions, as result statistics does,
    # while executable and full reference-image identities remain mandatory.
    rvas={0x682da0:16,0x680b70:16,0x896870:16,0x8a1400:16}
    raw=Path(__file__).with_suffix('.js').read_text('utf8')
    if raw.count('__RAID_POWER_PINS__')!=1:raise ValueError('Raid native CP source anchor')
    return raw.replace('__RAID_POWER_PINS__',json.dumps({r:snapshot[r:r+n].hex()for r,n in rvas.items()}))

def compose(snapshot,executable_sha256,template):
    anchor=" for(const [r,h]of Object.entries(pins))if(bytes(module.base.add(+r))!==h)throw Error('Native power sync identity '+r);"
    if template.count(anchor)!=1:raise ValueError('Raid native CP original bootstrap anchor')
    return source(snapshot,executable_sha256)+'\n'+template.replace(anchor,anchor+'\n installElsRaidNativePower();')
