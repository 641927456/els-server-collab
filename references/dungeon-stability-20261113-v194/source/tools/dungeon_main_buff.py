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
    passive_scope=json.loads((HERE/'dungeon_passive_buff_scope.json').read_text(encoding='utf-8'))
    states=sorted((s for r in passive_scope['rows'] for s in r['states']),key=lambda s:s['factor'])
    passive_factors={s['factor']:s['template'] for s in states}
    if len(passive_factors)!=len(states) or set(passive_factors)&set(factors):
        raise ValueError('Overlapping dungeon buff factors')
    modes={'dungeon':'PASSIVE_DUNGEON','parent':'PASSIVE_PARENT',
           'awakening':'PASSIVE_AWAKENING','red_moon':'PASSIVE_RED_MOON','patrona':'PASSIVE_PATRONA',
           'combat':'PASSIVE_COMBAT','third_awakening':'PASSIVE_THIRD_AWAKENING',
           'electron':'PASSIVE_ELECTRON','golden_oath':'PASSIVE_GOLDEN_OATH'}
    passive_cases='\n'.join(
        f'  case {s["factor"]}: return template_id=={s["template"]} ? {modes[s["mode"]]} : PASSIVE_NONE;'
        for s in states
    )
    parent_cases=[]
    for s in states:
        if 'parents' not in s:
            continue
        options=' || '.join(f'(factor=={p["factor"]} && template_id=={p["template"]})' for p in s['parents'])
        parent_cases.append(f'  case {s["factor"]}: return {options};')
    raw=(HERE/'dungeon_main_buff.c').read_text(encoding='utf-8')
    for marker,generated in [('__MAIN_FACTORS__',cases),('__PASSIVE_FACTORS__',passive_cases),
                             ('__PASSIVE_PARENTS__','\n'.join(parent_cases))]:
        if raw.count(marker)!=1:
            raise ValueError('Dungeon buff C source anchor '+marker)
        raw=raw.replace(marker,generated)
    return raw,factors,passive_factors
def source(snapshot,executable_sha256):
    if executable_sha256!=EXE_SHA or hashlib.sha256(snapshot).hexdigest()!=IMAGE_SHA:
        raise ValueError('Dungeon main buff client/image identity')
    code,factors,passive_factors=c_source()
    # Full patched method and native weak accessors; getter is an unwind-free leaf.
    ranges={0x11b0130:0x11b0309,0x11af720:0x11af8b1,0x15a0b0:0x15a0ff,0x15a100:0x15a15c,0x8571d0:0x8571f8,
            0x16ae290:0x16ae2a0,0x17394e0:0x1739f05,0x1771b10:0x1772386,
            0xf18400:0xf185c5,0x3b97d0:0x3b97d9,
            0x11507e0:0x1150803,0x119d670:0x119d72a,0x119d730:0x119d744,
            0x11a1f60:0x11a1fa7,0x1c19870:0x1c198a8,0x7d8b40:0x7d8b6d,
            0x1c22ba0:0x1c22c29,0x2066b00:0x2066b3d,0x1ffc922:0x1ffc94d,
            0x1f96735:0x1f9674c,0x20aae17:0x20aae32,
            0x2084354:0x208438c,0x1aa4580:0x1aa461b,0x119b6c7:0x119b740,0x43707e4:0x43707e8}
    arm_block=snapshot[0x16ae290:0x16ae2a0]
    if arm_block.hex()!='f30f5c8634040000f30f118630ae0100':raise ValueError('Arm lifetime native block')
    virtuals={0x41c2110+8:0x119b540,0x41c2110+0x20:0x119d110,0x41c2110+0x70:0x119d370,
              0x41c2110+0x78:0x119d670,0x41c2110+0x80:0x119d730,
              0x41c48f8+8:0x11507e0,0x41c1c10+8:0x11a1f60,0x41bfd28+0x150:0x1aa4580}
    for slot,rva in virtuals.items():
        if struct.unpack_from('<Q',snapshot,slot)[0]!=0x140000000+rva:
            raise ValueError('Dungeon buff virtual identity')
    profile=dict(update=0x11b0130,restore=0x11af720,arm_site=0x16ae290,arm_resume=0x16ae2a0,arm_block=list(arm_block),
                 archenemy=0x17394e0,archenemy_mod=0x1771b10,main_effect=0xf18400,set_effect_lifetime=0x3b97d0,
                 game_handle=0x478cb88,dungeon_vtable=0x41bfd28,
                 time_vtable=0x41c2110,valid_game=0x15a0b0,resolve_game=0x15a100,
                 my_actor=0x8571d0,native_virtuals=virtuals,factors=factors,
                 patrona_mp_update=0x11507e0,patrona_mp_vtable=0x41c48f8,
                 time_remaining=0x119d730,set_time_remaining=0x119d670,passive_factors=passive_factors,
                 awakening_remaining=0x7d8b40,
                 skill_buff_check=0x1c22ba0,electron_probability_return=0x2066b1d,
                 electron_attack_return=0x1ffc936,
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
