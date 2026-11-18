"""Pinned isolated candidate; compose into the actual release parent, never install here."""
from pathlib import Path
import hashlib,json,struct
HERE=Path(__file__).resolve().parent
EXE_SHA='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
IMAGE_SHA='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
ANCHOR=" for(const [r,h]of Object.entries(pins))if(bytes(module.base.add(+r))!==h)throw Error('Native power sync identity '+r);"
def c_source():
    scope=json.loads((HERE/'authorized-main-state-scope.json').read_text(encoding='utf-8'))
    factors={s['factor']:s['template']for r in scope['rows']for s in r['main_factors']}
    assert len(factors)==31
    cases='\n'.join(f'  case {fid}: return template_id=={tid};'for fid,tid in sorted(factors.items()))
    raw=(HERE/'dungeon_main_buff.c').read_text(encoding='utf-8')
    assert raw.count('__MAIN_FACTORS__')==1
    return raw.replace('__MAIN_FACTORS__',cases),factors
def source(snapshot,executable_sha256):
    if executable_sha256!=EXE_SHA or hashlib.sha256(snapshot).hexdigest()!=IMAGE_SHA:
        raise ValueError('Dungeon main buff client/image identity')
    code,factors=c_source()
    # Full patched method and native weak accessors; getter is an unwind-free leaf.
    ranges={0x11b0130:0x11b0309,0x11af720:0x11af8b1,0x15a0b0:0x15a0ff,0x15a100:0x15a15c,0x8571d0:0x8571f8,
            0x16ae290:0x16ae2a0,0x17394e0:0x1739f05,0x1771b10:0x1772386,
            0xf18400:0xf185c5,0x3b97d0:0x3b97d9}
    arm_block=snapshot[0x16ae290:0x16ae2a0]
    if arm_block.hex()!='f30f5c8634040000f30f118630ae0100':raise ValueError('Arm lifetime native block')
    virtuals={8:0x119b540,0x20:0x119d110,0x70:0x119d370}
    for slot,rva in virtuals.items():
        if struct.unpack_from('<Q',snapshot,0x41c2110+slot)[0]!=0x140000000+rva:
            raise ValueError('Dungeon main buff time virtual identity')
    profile=dict(update=0x11b0130,restore=0x11af720,arm_site=0x16ae290,arm_resume=0x16ae2a0,arm_block=list(arm_block),
                 archenemy=0x17394e0,archenemy_mod=0x1771b10,main_effect=0xf18400,set_effect_lifetime=0x3b97d0,
                 game_handle=0x478cb88,dungeon_vtable=0x41bfd28,
                 time_vtable=0x41c2110,valid_game=0x15a0b0,resolve_game=0x15a100,
                 my_actor=0x8571d0,timer_virtuals=virtuals,factors=factors,
                 bodies={start:snapshot[start:end].hex()for start,end in ranges.items()},
                 executable_sha256=EXE_SHA,image_sha256=IMAGE_SHA)
    raw=(HERE/'dungeon_main_buff.js').read_text(encoding='utf-8')
    for marker in ['__DUNGEON_MAIN_BUFF_PROFILE__','__DUNGEON_MAIN_BUFF_C__']:
        if raw.count(marker)!=1:raise ValueError('Dungeon main buff source anchor')
    stub=(HERE/'dungeon_arm_stub.js').read_text(encoding='utf-8')
    return stub+'\n'+raw.replace('__DUNGEON_MAIN_BUFF_PROFILE__',json.dumps(profile,separators=(',',':'))).replace('__DUNGEON_MAIN_BUFF_C__',json.dumps(code))
def compose(snapshot,executable_sha256,template):
    if template.count(ANCHOR)!=1:raise ValueError('Dungeon main buff startup anchor')
    return source(snapshot,executable_sha256)+'\n'+template.replace(ANCHOR,ANCHOR+'\n installElsDungeonMainBuffOnce();')
