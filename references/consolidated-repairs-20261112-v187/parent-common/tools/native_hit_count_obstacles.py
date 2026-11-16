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
 return obstacles



def exchange_source(image):
 if hashlib.sha256(image).hexdigest()!=IMAGE_SHA:raise ValueError('Fashion exchange image identity')
 folder=Path(__file__).parent
 pins={r:image[r:r+12].hex()for r in(LUA_BUFFER_LOADER,LUA_TAIL_DISPATCH)}
 contract=dict(loader=LUA_BUFFER_LOADER,pins=pins,
               resources=json.loads((folder/'native_shadow_castle.json').read_bytes())
                         +json.loads((folder/'native_lithia_memory1.json').read_bytes()))
 transform=(folder/'native_shadow_castle.js').read_text('utf8')
 transform=transform.replace('__SHADOW_CASTLE_CONTRACT__',json.dumps(contract,separators=(',',':')))
 event="event:'shadow_castle_native_resource_loaded'"
 assert transform.count(event)==1
 transform=transform.replace(event,"event:this.resource==='ItemExchangeTable.lua'?" 
    "'hidden_fashion_native_resource_loaded':'shadow_castle_native_resource_loaded'")
 transform+="\nsend({event:'hidden_fashion_native_support_ready',resource_count:1});"
 # Initial item tables can load before the existing dungeon support starts.
 return """(() => {
 const base=Process.getModuleByName('x2_dx11.exe').base;
 const pins=__FASHION_PINS__;
 let attempts=0;
 const timer=setInterval(install,5);
 function install(){
  if(++attempts>6000){clearInterval(timer);throw Error('Fashion exchange loader did not initialize');}
  if(!Object.entries(pins).every(([offset,hex])=>
      Array.from(new Uint8Array(base.add(Number(offset)).readByteArray(hex.length/2)),
                 value=>value.toString(16).padStart(2,'0')).join('')===hex))return;
  clearInterval(timer);
  __FASHION_TRANSFORM__
 }
 install();
})();""".replace('__FASHION_PINS__',json.dumps(pins)).replace('__FASHION_TRANSFORM__',transform)
