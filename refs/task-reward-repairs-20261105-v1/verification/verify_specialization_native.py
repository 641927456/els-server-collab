"""Original6E7 writer and6E8/item readers in private offline Unicorn memory."""
from pathlib import Path
import json,struct,sys
HERE=Path(__file__).resolve().parent;ROOT=Path('G:/els')
sys.dont_write_bytecode=True;sys.path[:0]=[str(HERE/'runtime'),str(HERE/'runtime/vendor'),str(ROOT/'tools')]
from els_server.domain.pvp_specialization import request,catalog
from els_server.protocol.spell_socket_messages import acknowledgement
from els_server.domain.inventory_items import item_body
from role_native_replay import Replay,IMAGE_SHA
rows=[]
def head(r,n):
 p=r.alloc(n);r.write(p,struct.pack('<QQQ',p,p,p)+b'\1\1');return p
def tree(r,size,key,value):
 h=head(r,size);p=r.alloc(size)
 r.write(h,struct.pack('<QQQ',p,p,p)+b'\1\1');r.write(p,struct.pack('<QQQ',h,h,h))
 r.write(p+0x20,struct.pack('<i',key));r.write(p+0x28,value);return h
for mode in(11,12):
 for group in(22,23,24):
  r=Replay();uid=2**40+9001;slot=4
  choice=0 if mode==11 else int(next(k for k,v in catalog()['series'].items()if v['group']==group))
  inner=tree(r,0x30,slot,struct.pack('<Q',choice))
  outer=tree(r,0x38,group,struct.pack('<QQ',inner,1))
  dto=r.alloc(0x20);r.write(dto,struct.pack('<QQQBiB',uid,outer,1,0,mode,0))
  packet=r.alloc(0x90);r.write(r.stack-8+0x28,struct.pack('<Q',dto))
  r.call(0x1323cc0,packet,0,0,0)
  start,end,cap=struct.unpack('<QQQ',r.read(packet+0x3e,24))
  wire=r.read(start,end-start);assert len(wire)==38 and request(wire)==(uid,group,slot-1,choice,mode)
  rows.append(dict(writer='1323CC0',mode=mode,group=group,wire_hex=wire.hex()))
gear=dict(uid=2**40+9010,template=700335,metadata=1,count=1,group=1,slot=0,durability=10000,enhancement=9,option_groups={'22':[141000131,141000140,0,0],'23':[141000001,0,0,0],'24':[142000001,0,0,0]})
for result in(0,2005):
 r=Replay();ack=acknowledgement(gear['uid'],987654321,[((1,0),gear),((3,2),None)],mode=12,ap=54321,result=result)
 data=r.alloc(len(ack.payload));r.write(data,ack.payload);buf=r.alloc(48);r.write(buf+8,struct.pack('<QQQ',data,data+len(ack.payload),data+len(ack.payload)))
 dto=r.alloc(0x60);r.call(0x234c870,buf,dto)
 consumed=int.from_bytes(r.read(buf+32,4),'little');assert consumed==len(ack.payload)
 assert struct.unpack('<iQQ',r.read(dto,20))==(result,gear['uid'],987654321)
 assert struct.unpack('<iii',r.read(dto+0x2c,12))==(12,0,54321)
 decoded=r.item(item_body(gear));assert decoded['ok']==1
 raw=bytes.fromhex(decoded['dto'])
 for group,values in gear['option_groups'].items():
  begin,end,cap=struct.unpack_from('<QQQ',raw,0x25+24*int(group))
  assert list(struct.unpack('<4i',r.read(begin,end-begin)))==values
 rows.append(dict(reader='234C870+D9A550',result=result,AP=54321,bytes=consumed,all_three_groups=True))
report=dict(ok=True,image_sha256=IMAGE_SHA,rows=rows,producer_path='3426350 ApplyOption/ApplyEnchant ->302B570 cases18190/18191 ->1317FC0 ->1323CC0; modes12/11, slot1..4, selected group ID sign-extended toQ',
 native_AP_field='234C870 DTO+34 ->302CEF0 unit currency+1A8',live_process_access=False,natural_GUI=False,world_gate_not_executed=True)
(HERE/'specialization-native-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(dict(ok=True,native_cases=len(rows))))
