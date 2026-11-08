"""Original ACK override and automatic admission segments in private Unicorn RAM."""
import json,struct
from unittest.mock import patch
from verify import PetCooldownTests,OUT,use,request,tail
from role_native_replay import Replay,IMAGE_SHA
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import *

fixture=PetCooldownTests();fixture.setUp()
rows=[]
try:
    r=Replay()
    actor=r.alloc(0x17000);frame=r.alloc(0x500)
    ctx=r.alloc(0x300);manager=r.alloc(0x600);pet_manager=r.alloc(0x600)
    head=r.alloc(0x40);node=r.alloc(0x40);clock=r.alloc(16)
    r.write(manager+0x5e8,struct.pack('<Q',pet_manager))
    r.write(ctx+0x140,struct.pack('<Q',head))
    r.write(head+8,struct.pack('<Q',node));r.write(head+25,b'\x01')
    r.write(node,struct.pack('<QQQ',head,head,head))
    r.write(node+28,struct.pack('<iii',1,0,0))
    r.write(r.base+0x3ea9ff0,struct.pack('<Q',clock))
    ticks=[0]
    r.write(clock,b'\xc3')
    r.uc.hook_add(UC_HOOK_CODE,lambda uc,address,size,user:r.finish_shim(ticks[0]),begin=clock,end=clock)
    frequency=struct.unpack('<d',r.read(r.base+0x4371410,8))[0]
    assert frequency==1000.,frequency

    def native_duration(override):
        # A different actor modifier is an explicit fixture, not a player claim.
        coefficient=.5;encoded=actor+0x16e78;mask=0xa53c9170
        bits=struct.unpack('<I',struct.pack('<f',coefficient))[0]
        r.write(encoded+8,struct.pack('<I',mask))
        r.write(encoded+16,struct.pack('<I',(encoded&0xffffffff)^mask^bits))
        r.write(frame+0x441,struct.pack('<f',override))
        for register,value in ((UC_X86_REG_RSP,r.stack-0x300),(UC_X86_REG_RBP,frame),
                (UC_X86_REG_R15,actor),(UC_X86_REG_R14,30),(UC_X86_REG_XMM6,0xbf800000)):
            r.uc.reg_write(register,value)
        r.uc.emu_start(r.base+0x3056073,r.base+0x30560c5,count=1000)
        assert r.uc.reg_read(UC_X86_REG_RIP)==r.base+0x30560c5
        return r.uc.reg_read(UC_X86_REG_R14)&0xffffffff

    def native_ready(slot,duration,elapsed,configured_remaining=0):
        r.write(node+36,struct.pack('<i',duration))
        r.write(pet_manager+0x548+4*slot,struct.pack('<f',configured_remaining))
        ticks[0]=round(elapsed*frequency)
        for register,value in ((UC_X86_REG_RSP,r.stack-0x300),(UC_X86_REG_R9,manager),
                (UC_X86_REG_R13,ctx),(UC_X86_REG_R14,slot),(UC_X86_REG_RDX,1),(UC_X86_REG_RDI,0)):
            r.uc.reg_write(register,value)
        r.uc.emu_start(r.base+0x305dd72,r.base+0x305de12,count=1000)
        assert r.uc.reg_read(UC_X86_REG_RIP)==r.base+0x305de12
        return bool(r.uc.reg_read(UC_X86_REG_RDI)&255)

    with patch('els_server.storage.pet_support.active_effects',return_value={'m_fReduceRecoveryItemCooltime':.055}):
        for slot in (0,1):
            answer=use(fixture.path,fixture.uid,request(slot),'native-'+str(slot),now=1000,automatic_use=True)
            override=tail(answer[0])[2]
            old=native_duration(-1.);new=native_duration(override)
            assert (old,new)==(15,29)
            assert native_ready(slot,old,15)
            assert not native_ready(slot,new,15)
            assert not native_ready(slot,new,28.999)
            assert native_ready(slot,new,29)
            assert not native_ready(slot,new,30,1)
            rows.append(dict(slot=slot,wire_cooldown=override,old_native_duration=old,
                actual_native_duration=new,blocked_at_seconds=[15,28.999],ready_at_seconds=29,
                configured_interval_still_blocks=True))
    result=dict(ok=True,image_sha256=IMAGE_SHA,checks=rows,
        segments=[['0x3056073','0x30560c5'],['0x305dd72','0x305de12']],
        clock='Explicit millisecond clock shim only for admission segment',
        live_game=False,natural_GUI=False,whole_functions_executed=False)
    (OUT/'native-tests.json').write_text(json.dumps(result,indent=2),'utf8')
    print(json.dumps(result,indent=2))
finally:
    fixture.doCleanups()
