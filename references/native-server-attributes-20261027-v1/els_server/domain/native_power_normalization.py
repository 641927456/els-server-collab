"""Original 988320 transform, independent of actor-source acquisition.

All raw fields and both maps are explicit. This module neither invents missing
actor inputs nor writes a character cache. Map insertion allocation is a host
container operation; the first original composition covers existing keys only.
"""
import math
from els_server.domain.native_power_kernel import f32
from els_server.domain.native_power_slopes import normalize

RAW_FIELDS=frozenset((0xf4,0x198,0x360,0x364,0x180,0x188,0x114,0x374,
                     0x410,0x18,0x110,0x1c,0x20,0x14,0x10,0x4f0,0x118))
LEAVES={0x7b8:(0xf4,0x987de0),0x7bc:(0x198,0x987e90),
        0x7c8:(0x180,0x987f50),0x7d0:(0x188,0x987f50),
        0x7d8:(0x114,0x988000),0x7e4:(0x18,0x9880d0),
        0x7e8:(0x110,0x988180),0x7f4:(0x14,0x9880d0),
        0x7f8:(0x10,0x9880d0)}

def finite(value):
    if type(value) not in (int,float) or not math.isfinite(value):
        raise ValueError('finite numeric input required')
    try: value=f32(value)
    except (OverflowError,struct_error): raise ValueError('float32 range') from None
    if not math.isfinite(value): raise ValueError('float32 range')
    return value

# f32 uses struct.pack; retain a narrow exception rather than swallowing errors.
from struct import error as struct_error

def checked_map(values):
    if type(values) is not dict or len(values)>1024:
        raise ValueError('bounded explicit int-float map required')
    if any(type(k) is not int or not -2**31<=k<2**31 for k in values):
        raise ValueError('signed int32 map keys required')
    return {k:finite(v) for k,v in values.items()}

def normalize_988230(value):
    x=finite(value)
    if x<=20.: y=x
    elif x<=35.: y=f32(f32(f32(x-20.)*f32(.85))+20.)
    elif x<=45.: y=f32(f32(f32(x-35.)*f32(.75))+32.75)
    elif x<=60.: y=f32(f32(f32(x-45.)*f32(.65))+40.25)
    else: y=50.
    return f32(y*f32(.01))

def transform(raw,map798,map7a8):
    if type(raw) is not dict or set(raw)!=RAW_FIELDS:
        raise ValueError('all 17 original raw fields required')
    raw={k:finite(v) for k,v in raw.items()}
    before=checked_map(map798); copied=checked_map(map7a8)
    derived={dst:normalize(leaf,raw[src]) for dst,(src,leaf) in LEAVES.items()}
    derived[0x7ec]=normalize_988230(raw[0x1c])
    for dst,src,limit in ((0x7c0,0x360,.2),(0x7c4,0x364,.2),
                          (0x7dc,0x374,.45),(0x7e0,0x410,.35),
                          (0x7f0,0x20,40.),(0x800,0x4f0,.6),
                          (0x7fc,0x118,.6)):
        derived[dst]=min(raw[src],f32(limit))
    copied.update(before)
    limited={k:min(v,f32(.35)) if k in (6,14,15,16) else 0. for k,v in before.items()}
    raw_after=dict(raw);raw_after[0x4f0]=min(100.,max(0.,raw[0x4f0]))
    return dict(derived=derived,raw_after=raw_after,map798=limited,map7a8=copied)
