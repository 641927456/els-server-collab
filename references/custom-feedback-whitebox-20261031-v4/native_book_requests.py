"""Original22611D0 argument builder -> originalC595C0 encoder, offline only."""
from pathlib import Path
import json,struct,sys
E=Path(__file__).resolve().parent;R=Path('G:/els');V=R/json.loads((R/'releases/local/current.json').read_bytes())['path'];sys.path[:0]=[str(V),str(R/'tools'),str(R/'tools/pylibs')]
from els_server.domain.character_custom import catalog
from role_native_replay import Replay,IMAGE_SHA
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_R8,UC_X86_REG_RDX
r=Replay();captured=[];args=[]
for target,fn in((0x3ae3a38,r.allocate),(0x4f40a0,r.free)):r.uc.hook_add(UC_HOOK_CODE,fn,begin=r.base+target,end=r.base+target)
seq=r.alloc(16);r.uc.hook_add(UC_HOOK_CODE,lambda *a:r.finish_shim(17),begin=seq,end=seq)
def dispatch(*a):
 p=r.uc.reg_read(UC_X86_REG_R8);args.append(r.read(p,64));r.finish_shim(1)
r.uc.hook_add(UC_HOOK_CODE,dispatch,begin=r.base+0xc4cc70,end=r.base+0xc4cc70)
def send(*a):
 p=r.uc.reg_read(UC_X86_REG_RDX);start,end,cap=struct.unpack('<QQQ',r.read(p+62,24));captured.append(r.read(start,end-start).hex());r.finish_shim(1)
r.uc.hook_add(UC_HOOK_CODE,send,begin=r.base+0x682d80,end=r.base+0x682d80)
root=r.alloc(0x400);r.write(root+0x198,struct.pack('<QQQ',0,0,0));r.write(r.base+0x4817e80,struct.pack('<Q',root));network=r.alloc(0x200);r.write(r.base+0x4817e70,struct.pack('<Q',network));obj=r.alloc(0x120);vt=r.alloc(0x60);r.write(vt+0x50,struct.pack('<Q',seq));r.write(obj,struct.pack('<Q',vt));r.write(obj+0x118,struct.pack('<I',1))
rows=[];rules=catalog();books=[166596,461428,480416,480141,470012,470523,next(k for k,v in rules.items()if v['type']==1 and 5 in v['units'])]
for family in(15,24):books.append(next(k for k,v in rules.items()if v['type']==family and 5 in v['units']))
for i,book in enumerate(books):
 rule=rules[book];uid=9801000+i;cid=rule['custom_ids'][0];family=rule['type'];r.write(root+0x1a0,r.read(root+0x198,8));r.write(r.stack-8+0x28,struct.pack('<I',0));assert r.call(0x22611d0,0,uid,cid,family)&255==1,book
 a=args[-1];assert struct.unpack_from('<QQii',a)==(uid,cid,family,0)
 p=r.alloc(64);r.write(p,a);r.write(r.stack-8+0x30,struct.pack('<Q',p));r.call(0xc595c0,obj,0,0,0);raw=bytes.fromhex(captured[-1]);assert struct.unpack('>QQiiIB',raw)==(uid,cid,family,0,0,0)
 rows.append(dict(book=book,uid=uid,custom_id=cid,family=family,payload=raw.hex()))
value=dict(ok=True,image_sha256=IMAGE_SHA,original_functions=['221F5D0 call arguments inspected','22611D0 builder executed','C595C0 encoder executed'],rows=rows,offline_only=True,natural_GUI=False,client_changes=False)
(E/'native-book-result.json').write_text(json.dumps(value,indent=2)+'\n','utf8');print(json.dumps(dict(ok=True,books=len(rows),families=sorted({r['family']for r in rows}),nonzero_target_and_family=True)))
