"""Original option2C0 integer MP leaf through pre-scale and ordinary merge."""
from els_server.domain.native_power_kernel import f32
from els_server.domain.native_option_metadata import ordinary_entry


def integer(value):
    if type(value)is not int or not -2**31<=value<2**31:
        raise ValueError('Original signed MP integer required')
    return value


def truncate(value):
    # SSE cvttss2si returns INT_MIN for a finite input outside signed32 range.
    value=f32(value)
    return int(value) if -2**31<=value<2**31 else -2**31


def source_value(definition):
    value=definition.get('m_iAddMpValue')
    return 0 if value is None else integer(value)


def merge(destination,source,meta,*,mode,resonance_level,unit_line,rank_factor,weight):
    destination=integer(destination);source=integer(source)
    if not ordinary_entry(meta,resonance_level=resonance_level,mode=mode):
        return destination
    if mode==1 and meta['native_1f5']==1 and meta['level_linked']==1:
        return destination
    if meta['source_line'] and meta['source_line']!=unit_line:
        return destination
    coefficient=rank_factor if meta['rank_linked']==1 else 0. if meta['pve_rank_linked']==1 else 1.
    scaled=truncate(f32(f32(source)*f32(coefficient)))
    pvp=bool(mode) and not(meta['rank_linked']==1 or meta['pve_rank_linked']==1)
    factor=f32(f32(meta['pvp_rate'] if pvp else 1.)*f32(weight))
    return truncate(f32(f32(f32(scaled)*factor)+f32(destination)))
