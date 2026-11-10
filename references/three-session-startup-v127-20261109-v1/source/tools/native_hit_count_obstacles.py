"""Build the pinned native dungeon mechanism support."""
from pathlib import Path
import hashlib,json
IMAGE_SHA='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
ENTRIES=(0x159670,0x1aa4a40,0x7d5560,0x7d8b00,0x16e3a00,0x16e14a0)
LUA_BUFFER_LOADER=0x3933fe0
LUA_TAIL_DISPATCH=0x16fee8
def source(image):
 if hashlib.sha256(image).hexdigest()!=IMAGE_SHA:raise ValueError('Hit-count obstacle image identity')
 text=Path(__file__).with_suffix('.js').read_text('utf8')
 assert text.count('__HIT_COUNT_PINS__')==1
 obstacles=text.replace('__HIT_COUNT_PINS__',json.dumps({r:image[r:r+12].hex()for r in ENTRIES}))
 folder=Path(__file__).parent
 castle=(folder/'native_shadow_castle.js').read_text('utf8')
 assert castle.count('__SHADOW_CASTLE_CONTRACT__')==1
 contract=dict(loader=LUA_BUFFER_LOADER,
               pins={r:image[r:r+12].hex()for r in(LUA_BUFFER_LOADER,LUA_TAIL_DISPATCH)},
               resources=json.loads((folder/'native_shadow_castle.json').read_bytes())+json.loads((folder/'native_lithia_memory1.json').read_bytes()))
 return obstacles+'\n'+castle.replace('__SHADOW_CASTLE_CONTRACT__',json.dumps(contract,separators=(',',':')))
