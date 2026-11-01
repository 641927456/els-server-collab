from delivery_common import *
import struct,sys
sys.dont_write_bytecode=True;sys.path[:0]=[str(R/'tools'),str(R/'tools/pylibs'),str(R/'tools/launcher_testdeps')]
from role_native_replay import Replay,IMAGE_SHA
assert read(W/'public-acceptance.json')['ok'];cases=read(W/'public-wires.private.json');assert len(cases)==12
replay=Replay();proof=[]
for case in cases:
 wire=bytes.fromhex(case['wire_hex']);count=struct.unpack_from('>I',wire)[0];assert count==3
 data=replay.alloc(len(wire));replay.write(data,wire);buffer=replay.alloc(48);replay.write(buffer+8,struct.pack('<QQQ',data,data+len(wire),data+len(wire)))
 dto=replay.alloc(32);records=replay.alloc(count*0x408);replay.write(dto+4,struct.pack('<QQQ',records,records,records+count*0x408));replay.call(0x234b280,buffer,dto)
 begin,end,capacity=struct.unpack('<QQQ',replay.read(dto+4,24));consumed=int.from_bytes(replay.read(buffer+32,4),'little');result=int.from_bytes(replay.read(dto,4),'little',signed=True)
 assert result==0 and consumed==len(wire)and begin==records and end==capacity==records+count*0x408
 rows=[]
 for p in range(begin,end,0x408):
  raw=replay.read(p,0x408);rows.append(dict(uid=struct.unpack_from('<Q',raw)[0],group=raw[8],slot=struct.unpack_from('<h',raw,9)[0],template=struct.unpack_from('<I',raw,11)[0],count=struct.unpack_from('<i',raw,16)[0]))
 assert rows==case['expected'],case['label'];proof.append(dict(label=case['label'],wire_sha256=__import__('hashlib').sha256(wire).hexdigest(),consumed=consumed,result=result,rows_verified=3))
save(W/'public-native-verification.json',dict(ok=True,cases=proof,original_decoder_RVA='0x234b280',image_sha256=IMAGE_SHA,live_process_touched=False,natural_GUI=False,scope='Exact public own 105 payloads parsed by original x64 decoder; native inventory UI application not executed'))
print(json.dumps(dict(ok=True,public_original_native_decodes=len(proof),live_process_touched=False)))
