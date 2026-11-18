"""Run original stage NPC filtering, with private game/actor objects only."""
from pathlib import Path
import sys,struct,json
ROOT=Path('G:/els');W=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tools/pylibs')]
from role_native_replay import Replay,IMAGE_SHA
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_RIP
r=Replay();game=r.alloc(0x1800);actor=r.alloc(0x1b800);slots=r.alloc(8)
r.write(game,struct.pack('<Q',r.base+0x41bfd28));r.write(game+0x378,struct.pack('<QQ',slots,slots+8))
r.write(slots,struct.pack('<Q',actor));r.write(r.base+0x48163b8,bytes(8))
assert int.from_bytes(r.read(r.base+0x41bfd28+0x1f0,8),'little')==r.base+0x1aa57b0
assert int.from_bytes(r.read(r.base+0x41bfd28+0x230,8),'little')==r.base+0x8567d0
cases=[]
for game_type,reason,retained in [(2,3,True),(2,1,True),(1,3,False),(3,3,False),(2,0,False)]:
    r.write(game+0x2cc,struct.pack('<i',game_type));r.write(actor+0x1b140,struct.pack('<i',reason))
    before=r.read(actor,0x1b800);visited=[]
    def stop_before_destroy(uc,address,size,user):
        visited.append(address)
        uc.emu_stop()
    hook=r.uc.hook_add(UC_HOOK_CODE,stop_before_destroy,begin=r.base+0x16cde30,end=r.base+0x16cde30)
    try:
        if retained:assert r.call(0x1aa57b0,game)==1
        else:
            try:r.call(0x1aa57b0,game)
            except ValueError as e:assert str(e)=='Replay instruction limit'
            else:raise AssertionError('Nonretained actor did not select removal')
    finally:r.uc.hook_del(hook)
    assert bool(visited)!=retained
    assert r.read(actor,0x1b800)==before and r.read(slots,8)==struct.pack('<Q',actor)
    cases.append(dict(game_type=game_type,creation_reason=reason,retained=retained,
        full_function_returned=retained,stopped_before_removal=not retained))
out=dict(image_sha256=IMAGE_SHA,function='1AA57B0 (Game v1F0)',caller='103E610 stage initialization',
    type_getter='8567D0 -> game+2CC',enum='GAME_TYPE.GT_DUNGEON=2',
    creation_reason_field='NPC+1B140; 1AA90C0 writes its reason argument',cases=cases,
    original_image_unchanged=True,live_process=False,natural_GUI=False)
(W/'native-stage-retention.json').write_text(json.dumps(out,indent=2),encoding='utf8');print(json.dumps(out))
