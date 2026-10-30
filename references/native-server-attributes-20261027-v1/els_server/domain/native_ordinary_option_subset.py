"""Original88A180 ordinary callback's qualified51-scalar/13-data subset.

Source selection, condition containers, other scalar leaves and the final
aggregate are separate. This is not a complete actor or live dispatcher.
"""
from els_server.domain.native_power_kernel import f32
from els_server.domain.native_option_metadata import source_metadata,ordinary_entry
from els_server.domain.native_option_pre_scale import transform
from els_server.domain.native_option_record_merge import merge_option_record


def metadata(definition):
    result=source_metadata(definition)
    for name,key in(('rank_linked','m_bIsRankLinkedStat'),
                     ('pve_rank_linked','m_bIsPVERankLinkedStat'),
                     ('level_linked','m_bIsLevelLinkedStat')):
        value=definition.get(key)
        if value is None:value=0
        if type(value)is not int or not -2**31<=value<2**31:
            raise ValueError('Original flag integer required')
        result[name]=int(value!=0)
    value=definition.get('m_iAddLevel')
    if value is None:value=0
    if type(value)is not int or not -2**31<=value<2**31:
        raise ValueError('Original linked-level delta required')
    result['add_level']=value
    return result


def merge(destination,source,destination_data,source_data,meta,*,level,mode,
          resonance_level,unit_line,condition_value,rank_factor,weight):
    # The gate precedes all per-record contributions.
    if not ordinary_entry(meta,resonance_level=resonance_level,mode=mode):
        return dict(destination),tuple(destination_data)
    if mode==1 and meta['native_1f5']==1 and meta['level_linked']==1:
        if type(level)is not int or not 0<=level<=255:
            raise ValueError('Original item callback level required')
        if type(destination_data)is not tuple or len(destination_data)!=13 or type(source_data)is not tuple or len(source_data)!=13:
            raise ValueError('Complete thirteen data fields required')
        linked=f32((level+meta['add_level']+2**31)%2**32-2**31)
        data=list(map(f32,destination_data))
        for i in(6,8,7,12,11):data[i]=f32(f32(linked*f32(source_data[i]))+data[i])
        # This original branch ignores both callback weight and PvP rate.
        return dict(destination),tuple(data)
    coefficient=rank_factor if meta['rank_linked']==1 else 0. if meta['pve_rank_linked']==1 else 1.
    scaled,data=transform(source,source_data,coefficient)
    data=tuple(f32(v*f32(weight))for v in data)
    return merge_option_record(destination,scaled,destination_data,data,
        level=level,kind=meta['kind'],source_line=meta['source_line'],
        unit_line=unit_line,condition_enabled=meta['condition_enabled'],
        condition_kind=meta['condition_kind'],condition_scale=meta['condition_scale'],
        condition_value=condition_value,pvp=bool(mode)and not(meta['rank_linked']==1 or meta['pve_rank_linked']==1),
        pvp_rate=meta['pvp_rate'],weight=weight)
