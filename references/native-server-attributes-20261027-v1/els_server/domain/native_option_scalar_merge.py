"""Original9859A0 scalar phase over explicit normalized source leaves.

This phase preserves metadata predicates and rounding. Definition selection,
percentage-data merging and dynamic containers are distinct producer phases.
"""
from els_server.domain.native_power_kernel import f32
from els_server.domain.native_option_scalar_inputs import FIELDS as INPUT_FIELDS

FIELDS = INPUT_FIELDS - {0x6b8,0x6bc,0x6c0,0x6c4,0x6c8,0x6cc}
UNSCALED = frozenset((0x4f0,0x4f4,0x590,0x5e8,0x5ec))


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Explicit bounded native integer required')
    return value


def merge_scalar_phase(destination, source, *, kind, source_line, unit_line,
                       condition_enabled, condition_kind, condition_scale,
                       condition_value, pvp, pvp_rate, weight):
    if type(destination) is not dict or type(source) is not dict or set(destination)!=FIELDS or set(source)!=FIELDS:
        raise ValueError('Complete native scalar phase inputs required')
    d={k:f32(v) for k,v in destination.items()}
    s={k:f32(v) for k,v in source.items()}
    integer(kind,0,2**32-1);integer(source_line,0,65535);integer(unit_line,0,65535)
    integer(condition_enabled,0,255);integer(condition_kind,-2**31,2**31-1)
    integer(condition_value,-2**31,2**31-1)
    if type(pvp) is not bool:raise ValueError('Explicit native phase flag required')
    value=f32(condition_value);coefficient=f32(condition_scale)
    factor=f32((f32(pvp_rate) if pvp else 1.)*f32(weight))
    if source_line and source_line!=unit_line:return d
    for offset in FIELDS:
        if offset==0x558:
            d[offset]=max(d[offset],s[offset]);continue
        if offset in UNSCALED:
            contribution=s[offset]
        else:
            contribution=f32(factor*s[offset])
        if offset==0xf4:
            if kind in (458,459,474,475):contribution=s[offset]
            elif condition_enabled==1 and condition_kind==12:
                contribution=f32(contribution+value)
        elif offset==0xf8 and condition_enabled==1 and condition_kind==6:
            contribution=f32(f32(factor*coefficient)*value)
        elif offset==0x110 and condition_enabled==1 and condition_kind==8:
            contribution=f32(contribution*value)
        elif offset==0x118 and condition_enabled and condition_kind==2:
            contribution=f32(contribution+f32(value*f32(.01)))
        elif offset==0x11c and condition_enabled and condition_kind==1:
            contribution=f32(contribution+f32(value*f32(.01)))
        elif offset==0x198 and condition_enabled==1 and condition_kind==11:
            contribution=f32(contribution+value)
        elif offset==0x41c and condition_enabled==1 and condition_kind==4:
            contribution=f32(f32(f32(value*coefficient)+s[offset])*factor)
        d[offset]=f32(contribution+d[offset])
    return d
