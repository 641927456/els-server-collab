"""Pinned offline native ACK readers, including the actual digestion DTO field."""
import json,struct,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;BASE=HERE/'runtime';ROOT=Path('G:/els')
sys.dont_write_bytecode=True;sys.path[:0]=[str(BASE),str(BASE/'vendor'),str(ROOT/'tools')]
from els_server.protocol import pet_progression_messages as wire
from els_server.protocol.companion_messages import pet_record
from els_server.domain.fashion_state import move_ack
from els_server.domain.inventory_items import TEMPLATE_BAG_GROUPS
from role_native_replay import Replay,IMAGE_SHA
from verify_pet_support_offline import stream
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_RDX,UC_X86_REG_RSP,UC_X86_REG_RBP

pet=dict(uid=1001076,unit=3,name='DigestPet',step=2,satiety=4200,growth=123456,personality={},nutrition=17,digest_until=2000010800)
item=dict(uid=1001001,template=135977,metadata=2,count=2,group=4,slot=1)
item['group']=TEMPLATE_BAG_GROUPS[135977]
results=[]
for kind in(0x8ae,0x8ba):
    for result in(0,-1):
        r=Replay();observed={};pointers=[]
        payload=wire.nutrient(pet,updates=[item],result=result).payload if kind==0x8ae else wire.digestion(pet,result=result).payload
        _,buf=stream(r,payload)
        def pet_pointer(uc,*args):pointers.append(uc.reg_read(UC_X86_REG_RDX))
        if kind==0x8ba:r.uc.hook_add(UC_HOOK_CODE,pet_pointer,begin=r.base+0xd9c550,end=r.base+0xd9c550)
        def gate(uc,*args):
            if kind==0x8ba:
                p=pointers[-1]
                observed.update(uid=int.from_bytes(r.read(p,8),'little'),digest_until=int.from_bytes(r.read(p+0x3d,8),'little'),nutrition=int.from_bytes(r.read(p+0x45,2),'little'))
            else:
                bp=uc.reg_read(UC_X86_REG_RBP)
                observed.update(result=struct.unpack('<i',r.read(bp-0x30,4))[0],nutrition=int.from_bytes(r.read(bp-0x2c,2),'little'),digest_until=int.from_bytes(r.read(bp-0x2a,8),'little'),uid=int.from_bytes(r.read(bp-0xa,8),'little'))
            r.finish_shim(0) # Observe parsing only; the live request/world gate is not simulated.
        r.uc.hook_add(UC_HOOK_CODE,gate,begin=r.base+0x74ffa0,end=r.base+0x74ffa0)
        r.write(r.stack-8+0x28,struct.pack('<Q',buf))
        r.call(0x2dcd260 if kind==0x8ae else 0x2dcd700,r.alloc(0x600),0,0,0)
        consumed=int.from_bytes(r.read(buf+32,4),'little')
        assert consumed==len(payload),(kind,consumed,len(payload))
        assert all(observed[k]==pet[k]for k in('uid','nutrition','digest_until')),observed
        if kind==0x8ae:assert observed['result']==result
        results.append(dict(kind=hex(kind),result=result,bytes=consumed,observed=observed))
report=dict(ok=True,image_sha256=IMAGE_SHA,rows=results,live_process_access=False,GUI_acceptance=False,terminal_world_gate_observed_only=True)
(HERE/'pet-native-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print(json.dumps(dict(ok=True,native_readers=len(results))))
