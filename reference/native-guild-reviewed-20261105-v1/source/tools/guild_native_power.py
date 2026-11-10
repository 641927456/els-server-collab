"""Qualified native CP only in the original current Guild Expedition signup."""
from pathlib import Path
import hashlib,json
EXE_SHA='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
IMAGE_SHA='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'

def source(snapshot,executable_sha256):
 if executable_sha256!=EXE_SHA or hashlib.sha256(snapshot).hexdigest()!=IMAGE_SHA:raise ValueError('Guild native power client identity')
 rvas={0x242f510:15,0x30dd8a4:22,0x24318b1:13,0x3b6da30:16,
       0x896870:16,0x3b6dbd0:16,0x3b6dda0:16,0x3b6dcc0:16}
 raw=Path(__file__).with_suffix('.js').read_text('utf8')
 if raw.count('__GUILD_POWER_PINS__')!=1:raise ValueError('Guild power support source anchor')
 return raw.replace('__GUILD_POWER_PINS__',json.dumps({r:snapshot[r:r+n].hex()for r,n in rvas.items()}))

def compose(snapshot,executable_sha256,template):
 anchor=" for(const [r,h]of Object.entries(pins))if(bytes(module.base.add(+r))!==h)throw Error('Native power sync identity '+r);"
 if template.count(anchor)!=1:raise ValueError('Guild power original startup anchor')
 return source(snapshot,executable_sha256)+'\n'+template.replace(anchor,anchor+'\n installElsGuildNativePower();')
