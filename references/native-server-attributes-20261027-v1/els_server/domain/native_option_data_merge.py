"""Original985360 six data leaves plus seven direct STAT leaves.

The caller supplies original source eligibility and condition arguments. This
function does not infer a trigger, source ownership or set activation.
"""
from els_server.domain.native_power_kernel import f32


def signed(value):
    if type(value) is not int or not -2**31 <= value < 2**31:
        raise ValueError('Original int32 argument required')
    return value


def merge_attribute_data(destination, source, *, level_factor, condition_kind,
                         condition_value, condition_scale):
    if type(destination) is not tuple or type(source) is not tuple or len(destination)!=13 or len(source)!=13:
        raise ValueError('Complete original six-plus-seven source inputs required')
    d=list(map(f32,destination));s=tuple(map(f32,source))
    level=f32(signed(level_factor));kind=signed(condition_kind)
    value=f32(signed(condition_value));coefficient=f32(condition_scale)
    # Seven direct source stats precede the other calculations in985360.
    for index in range(6,13):d[index]=f32(s[index]+d[index])
    hp=f32(level*s[0])
    if kind==9:hp=f32(value*hp)
    d[0]=f32(d[0]+hp)
    d[1]=f32(s[1]+d[1])
    additional=f32(value*coefficient)
    if kind==5:
        d[2]=f32(additional+d[2]);d[3]=f32(additional+d[3])
    elif kind==13:
        d[2]=f32(f32(s[2]+additional)+d[2])
        d[3]=f32(f32(additional+s[3])+d[3])
    else:
        d[2]=f32(s[2]+d[2]);d[3]=f32(s[3]+d[3])
    if kind==7:
        d[4]=f32(additional+d[4]);d[5]=f32(additional+d[5])
    else:
        d[4]=f32(s[4]+d[4]);d[5]=f32(s[5]+d[5])
    return tuple(d)


STAT_KEYS=('m_fBaseHP','m_fAtkPhysic','m_fAtkMagic','m_fDefPhysic','m_fDefMagic')


def direct_option_stats(definition):
    """The current original STAT loader reads five named fields, not MaxHP."""
    if type(definition) is not dict or set(definition)-set(STAT_KEYS):
        raise ValueError('Unqualified original option STAT property')
    hp,physical,magical,physical_def,magical_def=(f32(definition[k]) if k in definition else 0. for k in STAT_KEYS)
    return (hp,physical,magical,0.,0.,physical_def,magical_def)


def level_factor(level):
    """98720F..987238; original float constants15 and85, then cvttss2si."""
    if type(level) is not int or not 0<=level<=99:
        raise ValueError('Qualified original role level0..99 required')
    return int(f32(f32(f32(level)*15.)+85.))
