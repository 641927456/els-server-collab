"""Build the one pinned native hit-count adapter; no resource patching."""
from pathlib import Path
import hashlib,json
IMAGE_SHA='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
ENTRIES=(0x159670,0x1aa4a40,0x7d5560,0x7d8b00,0x16e3a00,0x1695250)
def source(image):
 if hashlib.sha256(image).hexdigest()!=IMAGE_SHA:raise ValueError('Hit-count obstacle image identity')
 text=Path(__file__).with_suffix('.js').read_text('utf8')
 assert text.count('__HIT_COUNT_PINS__')==1
 return text.replace('__HIT_COUNT_PINS__',json.dumps({r:image[r:r+12].hex()for r in ENTRIES}))
