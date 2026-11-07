"""Execute unchanged producer instructions in private Unicorn memory."""
from pathlib import Path
import hashlib,json,struct,sys
R=Path('G:/els');H=Path(__file__).resolve().parent
sys.path[:0]=[str(R),str(R/'tools/pylibs')]
from tools.role_native_replay import Replay
r=Replay();sas=r.alloc(0x60)
def reset():r.write(sas+0x50,struct.pack('<I',1039))
def get():return r.call(0x1271e60,sas)&0xffffffff
def inc():r.call(0x3b817b0,sas)
reset();a=get();b=get();inc();inc()
assert(a,b,get())==(1039,1039,1041)
reset();serial=[]
for _ in range(2):serial.append(get());inc()
assert serial==[1039,1040]and get()==1041
image=(R/'analysis/client-6c6b5180/x2-runtime.bin').read_bytes()
report=dict(ok=True,image_sha256=hashlib.sha256(image).hexdigest(),native_code_changed=False,
            native_getter=image[0x1271e60:0x1271e64].hex(),native_increment=image[0x3b817b0:0x3b817b4].hex(),
            concurrent_reads=[a,b],serialized_reads=serial,final_counter=1041,
            scope='Original counter instructions; controlled interleaving, not a natural game reproduction',
            production_modified=False)
(H/'native-send-race.json').write_text(json.dumps(report,indent=2)+'\n','utf8');print(json.dumps(report))
