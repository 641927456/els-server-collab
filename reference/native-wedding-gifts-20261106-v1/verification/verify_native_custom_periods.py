"""Original4CD ownership consumer and4CB reader/producer for dated custom tuples."""
from pathlib import Path
import sys,ctypes,json,hashlib,struct,time
R=Path('G:/els');G=Path(__file__).resolve().parent;W=G.parents[1]
sys.dont_write_bytecode=True;sys.path[:0]=[str(G/'test-source-v1'),str(R/'tools'),str(R/'tools/pylibs'),str(R)]
ctypes.WinDLL(str(W/'duel-wire-v2/full-source/python/sqlite3.dll'))
import els_server
from role_native_replay import Replay,IMAGE_SHA
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_RDX
from els_server.domain.character_custom import canonical,data
from els_server.domain.custom_periods import customs,value
from els_server.protocol import character_custom_messages as wire
r=Replay();captured=[]
for target,fn in((0x3ae3a38,r.allocate),(0x4f40a0,r.free)):r.uc.hook_add(UC_HOOK_CODE,fn,begin=r.base+target,end=r.base+target)
sequence=r.alloc(16);r.write(sequence,b'\xc3');r.uc.hook_add(UC_HOOK_CODE,lambda *a:r.finish_shim(17),begin=sequence,end=sequence)
def observe(*a):
 p=r.uc.reg_read(UC_X86_REG_RDX);start,end,cap=struct.unpack('<QQQ',r.read(p+62,24));assert start<=end<=cap
 captured.append(dict(kind=struct.unpack('<H',r.read(p+52,2))[0],payload=r.read(start,end-start)));r.finish_shim(1)
r.uc.hook_add(UC_HOOK_CODE,observe,begin=r.base+0x682d80,end=r.base+0x682d80)
obj=r.alloc(0x120);vt=r.alloc(0x60);r.write(vt+0x50,struct.pack('<Q',sequence));r.write(obj,struct.pack('<Q',vt));r.write(obj+0x118,struct.pack('<I',1))
def stream(raw):
 p=r.alloc(len(raw));r.write(p,raw);buf=r.alloc(48);r.write(buf+8,struct.pack('<QQQ',p,p+len(raw),p+len(raw)));st=r.alloc(40);r.call(0x3b6d140,st);r.call(0x3b6d1c0,st,buf,0);return st,buf
root=r.alloc(0x1600);manager=root+0xdc8;flat=r.alloc(76*80);r.write(manager+0x270,struct.pack('<QQQ',flat,flat,flat+76*80));r.write(r.base+0x4817e80,struct.pack('<Q',root))
values=[canonical(cid)for cid in data()['sit_variant_corrections']['custom_ids']]
values.extend(value(cid,1793956000,1793956000+30*86400)for cid in customs());assert len(values)==65
for index,v in enumerate(values):
 raw=wire.registered(v).payload;st,buf=stream(raw);r.write(r.stack-8+0x28,struct.pack('<Q',buf))
 assert r.call(0xbb7f30,0,0,0,0)&255==1 and struct.unpack('<I',r.read(buf+32,4))[0]==len(raw)
 row=flat+index*76;assert struct.unpack('<ii',r.read(row,8))==(v['custom_id'],0)and struct.unpack('<i',r.read(row+72,4))[0]==v['variant']
 for offset,key in((8,'date1'),(40,'date2')):
  field=row+offset;length,capacity=struct.unpack('<QQ',r.read(field+16,16));ptr=struct.unpack('<Q',r.read(field,8))[0]if capacity>7 else field
  assert r.read(ptr,length*2).decode('utf-16le')==v[key]
 assert struct.unpack('<Q',r.read(manager+0x278,8))[0]==flat+(index+1)*76
 if v['custom_id']in customs():
  raw=wire.selection_map({7:v});st,buf=stream(raw);head=r.alloc(104);r.write(head,struct.pack('<QQQBB',head,head,head,1,1));mp=r.alloc(16);r.write(mp,struct.pack('<QQ',head,0))
  assert r.call(0x2bdf5d0,st,mp)&255==1 and struct.unpack('<I',r.read(buf+32,4))[0]==len(raw)
  r.write(r.stack-8+0x30,struct.pack('<Q',mp));r.call(0x125f700,obj,0,0,0)
  assert captured[-1]['kind']==0x4cb and captured[-1]['payload']==raw
report=dict(ok=True,image_sha256=IMAGE_SHA,offline_only=True,native_Game=False,natural_GUI=False,original_files_modified=False,registered=65,period_Apply_produced=16,checks=['OriginalBB7F30/11F2B10 retained both original date strings and exact Lu/Ciel variants for49 corrected permanent sits plus16 period sits','Original2BDF5D0 reader and125F700 producer round-tripped all16 dated Apply maps byte-for-byte'],shims=['CRT allocation/copy/free','sequence provider','final network sender observed'],source_pins={p.relative_to(G/'candidate').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in(G/'candidate').rglob('*')if p.is_file()})
out=G/('native-custom-periods-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,indent=2)+'\n','utf8');print(json.dumps(report|dict(evidence=str(out))))
