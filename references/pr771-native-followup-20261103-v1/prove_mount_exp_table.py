"""Execute original mount EXP registration and progress consumer, privately."""
from pathlib import Path
import hashlib,json,struct,sys
ROOT=Path('G:/els');W=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tools/pylibs')]
from role_native_replay import Replay,IMAGE_SHA
r=Replay();manager=r.alloc(0x180);head=r.alloc(0x30)
r.write(head,struct.pack('<QQQ',head,head,head));r.write(head+0x18,b'\x01\x01')
r.write(manager+0x128,struct.pack('<QQ',head,0))
path=ROOT/'analysis/pr771-remaining-20261103-v1/growth-resources/RidingPetData.lua.tables.json'
rows=[c['arguments'][1:]for c in json.loads(path.read_bytes())['__symbolic_calls__']if c['function'].endswith('.AddExpTable')]
assert len(rows)==20
for level,cumulative,span,unknown in rows:
    r.write(r.stack+0x20,struct.pack('<i',unknown))
    r.call(0xd81270,manager,level,cumulative,span)
assert int.from_bytes(r.read(manager+0x130,8),'little')==20
def find(level):
    p=int.from_bytes(r.read(head+8,8),'little')
    while p!=head:
        k=int.from_bytes(r.read(p+0x1c,4),'little')
        if k==level:return p
        p=int.from_bytes(r.read(p+(0 if level<k else 0x10),8),'little')
    raise AssertionError('Native tree row missing')
for level,cumulative,span,unknown in rows:assert struct.unpack('<3i',r.read(find(level)+0x20,12))==(cumulative,span,unknown)
exp=r.alloc(4);denominator=r.alloc(8);cases=[]
for level,value,expected in [(1,0,0),(2,200,0),(2,300,50),(14,6000,40),(14,6300,70),(15,6300,0),(20,11300,100)]:
    r.write(exp,struct.pack('<i',value));r.write(denominator,bytes(8))
    result=r.call(0xd813b0,manager,level,exp,denominator)&0xffffffff
    assert result==expected,(level,value,result)
    cases.append(dict(level=level,experience=value,percent=result,
        remaining_field=struct.unpack('<i',r.read(exp,4))[0],display_denominator=struct.unpack('<d',r.read(denominator,8))[0]))
out=dict(image_sha256=IMAGE_SHA,registration='D81270; bound at2AC8888 through2BD97D0',consumer='D813B0',
    source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),registered_rows=20,native_tree_payload_matches=True,cases=cases,
    meanings={'argument1':'level key','argument2':'cumulative EXP subtracted from the owned EXP',
        'argument3':'progress display denominator; not inferred to be a rank award',
        'argument4':'stored at node+28; not read by D813B0, gameplay meaning remains unverified'},
    source_row_14=[14,5600,1000,2],source_row_15=[15,6300,1000,1],
    native_table_not_rewritten=True,original_image_unchanged=True,private_Unicorn=True,live_process=False,
    rank_award_verified=False,upgrade_weights_verified=False,server_experience_awarded=False)
(W/'native-mount-exp-table.json').write_bytes((json.dumps(out,indent=2)+'\n').encode());print(json.dumps(out))
