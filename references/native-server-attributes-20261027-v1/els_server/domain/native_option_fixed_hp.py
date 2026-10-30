"""Original option530 fixed HP leaf, separate from percentage/STAT inputs."""
from els_server.domain.native_power_kernel import f32
from els_server.domain.native_ordinary_option_subset import metadata,ordinary_entry


def merge(current,definition,*,level,mode,resonance_level,unit_line,rank_factor,weight):
    value=f32(current);meta=metadata(definition)
    if not ordinary_entry(meta,resonance_level=resonance_level,mode=mode):return value
    # The PvP level-linked branch writes only five direct data fields.
    if mode==1 and meta['native_1f5']==1 and meta['level_linked']==1:return value
    if meta['source_line']and meta['source_line']!=unit_line:return value
    incoming=f32(definition['m_fIncreaseFixHP'])if 'm_fIncreaseFixHP'in definition else 0.
    # 9896FA..98970B copies530 without multiplying the rank/PvE coefficient.
    # 986BA2..986BB7 then applies the normal PvP/callback factor once.
    pvp=bool(mode)and not(meta['rank_linked']==1 or meta['pve_rank_linked']==1)
    factor=f32((meta['pvp_rate']if pvp else 1.)*f32(weight))
    return f32(value+f32(factor*incoming))
