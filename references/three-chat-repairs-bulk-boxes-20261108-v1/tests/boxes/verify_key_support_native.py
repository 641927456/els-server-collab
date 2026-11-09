"""Original collector plus original template lookup / preview validation."""
from bootstrap import *
import struct,hashlib
from role_native_replay import Replay,IMAGE_SHA
from verify_manufacture_material_native import tree
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import *
from els_server.game_data import client_data
spec=json.loads((OUT/'source/tools/owned_box_key_aliases.json').read_bytes());node=json.loads((OUT/'client-key-support-node.json').read_bytes());assert node['ok'];c=client_data();r=Replay()
r.uc.hook_add(UC_HOOK_CODE,lambda uc,*_:uc.emu_stop(),begin=r.stop,end=r.stop)
world=r.alloc(0x600);manager=r.alloc(0xa00);session=r.alloc(0x200);user=r.alloc(0x4000);game=r.alloc(0x400)
r.write(r.base+0x4817e70,struct.pack('<Q',world));r.write(r.base+0x4817e80,struct.pack('<Q',game));r.write(world+0x58,struct.pack('<Q',manager));r.write(world+0xc8,struct.pack('<Q',session));r.write(session+0xa0,struct.pack('<Q',user))
ids=sorted({r['template']for r in spec['rules']}|{v for row in spec['rules']for v in row['aliases'].values()});blob=r.alloc(16+236*len(ids));r.write(blob+8,struct.pack('<I',len(ids)))
for n,t in enumerate(ids):r.write(blob+16+n*4,struct.pack('<I',t));r.write(blob+16+4*len(ids)+n*232,c.item(t)['record'])
r.write(manager+0x30,struct.pack('<QQ',blob,blob+16+236*len(ids)));frame=r.alloc(0x200)
def validate(t,key):
 vector=r.alloc(24);data=r.alloc(4);r.write(data,struct.pack('<i',key));r.write(vector,struct.pack('<QQQ',data,data+4,data+4));sp=r.stack-8;r.write(sp,struct.pack('<Q',r.stop))
 for reg,value in((UC_X86_REG_RSP,sp),(UC_X86_REG_RCX,frame),(UC_X86_REG_RDX,t),(UC_X86_REG_R8,9001),(UC_X86_REG_R9,vector)):r.uc.reg_write(reg,value)
 r.uc.emu_start(r.base+0x2271a80,r.base+0x2271b76,count=100000)
 return r.uc.reg_read(UC_X86_REG_RIP)==r.base+0x2271b76
rows=[]
for proof in node['rows']:
 if proof['old']==proof['replacement']:continue
 t=proof['template'];old=proof['old'];new=proof['actual'];assert not validate(t,old),(t,old,'missing native template unexpectedly accepted')
 value=r.alloc(64);r.write(value,struct.pack('<4i',t,new,proof['required'],proof['give']));head=tree(r,[(t,value)],key_format='i');r.write(manager+0xb8,struct.pack('<Q',head));vector=r.alloc(24)
 assert r.call(0x6ac800,manager,vector,t)&255==1
 begin,end=struct.unpack('<QQ',r.read(vector,16));assert end-begin==4 and struct.unpack('<i',r.read(begin,4))[0]==new
 assert validate(t,new),(t,new,'canonical native preview validation')
 rows.append(dict(template=t,old=old,key=new,native_collector=True,original_missing_key_rejected=True,canonical_key_accepted=True,required_count_unchanged=proof['required'],give_count_unchanged=proof['give']))
report=dict(ok=True,image_sha256=IMAGE_SHA,rows=rows,aliases=len(rows),original_collector_RVA='6AC800',original_lookup_RVA='6D56C0',original_preview_validation='2271A80..2271B76',live_game=False,natural_GUI=False,private_emulated_native_memory=True)
(OUT/'client-key-support-native.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8');print(json.dumps(dict(ok=True,aliases=len(rows))))
