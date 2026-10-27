"""Original865660 six-float option contribution before resistance finalization."""
from els_server.domain.native_power_kernel import f32
from els_server.domain.native_extended_option_inputs import extended_source_inputs


def _flag(definition,key):
    value=definition.get(key)
    if value is None:return False
    if type(value)is not int or not -2**31<=value<2**31:
        raise ValueError('Original source int32 flag required')
    return value!=0


def merge(current,definition,*,rank_factor,pve_rank_factor,weight):
    if type(current)is not tuple or len(current)!=6:
        raise ValueError('Explicit original six resistance floats required')
    current=tuple(map(f32,current))
    rank_factor=f32(rank_factor);pve_rank_factor=f32(pve_rank_factor);weight=f32(weight)
    if definition is None:return current
    source=extended_source_inputs(definition)['source_resistances']
    # This consumer differs from ordinary88A180: PvE-rank linked resistance
    # calls the separate native PvE registry instead of forcing coefficient0.
    coefficient=rank_factor if _flag(definition,'m_bIsRankLinkedStat')else pve_rank_factor if _flag(definition,'m_bIsPVERankLinkedStat')else 1.
    coefficient=f32(coefficient*weight)
    return tuple(f32(f32(f32(v)*coefficient)+old)for old,v in zip(current,source))
