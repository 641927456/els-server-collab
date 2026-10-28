"""88A180 pre-scaling and gates for CP maps and conditional stat rows.

These outputs accompany the qualified scalar/data subset. Actor event-effect
containers and other option leaves are still separate producer contracts.
"""
from els_server.domain.native_power_kernel import f32
from els_server.domain.native_option_metadata import ordinary_entry
from els_server.domain.native_option_power_maps import merge_map_inputs
from els_server.domain.native_option_condition_inputs import append_condition


def merge(capability,probability,additional,conditions,source,row,meta,*,mode,
          resonance_level,unit_line,condition_value,rank_factor,weight):
    if (not ordinary_entry(meta,resonance_level=resonance_level,mode=mode)
            or mode==1 and meta['native_1f5']==1 and meta['level_linked']==1):
        return dict(capability),dict(probability),tuple(additional),tuple(conditions)
    coefficient=f32(rank_factor if meta['rank_linked']==1 else 0. if meta['pve_rank_linked']==1 else 1.)
    kind,basic,enchant=source['capability']
    scaled=dict(capability=(kind,f32(coefficient*f32(basic)),f32(coefficient*f32(enchant))),
        probability={k:f32(coefficient*f32(v))for k,v in source['probability'].items()},
        additional=source['additional'])
    cap,prob,add=merge_map_inputs(capability,probability,additional,scaled,
        condition_enabled=meta['condition_enabled'],condition_value=condition_value,
        pvp=bool(mode)and not(meta['rank_linked']==1 or meta['pve_rank_linked']==1),
        pvp_rate=meta['pvp_rate'],weight=weight,
        source_line=meta['source_line'],unit_line=unit_line)
    conditional=append_condition(conditions,row,source_line=meta['source_line'],unit_line=unit_line)
    return cap,prob,add,conditional
