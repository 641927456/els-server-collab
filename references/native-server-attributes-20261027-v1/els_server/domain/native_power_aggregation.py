"""Assemble896870's qualified sources in native order before89B430.

The caller supplies source-projected seven fields, effective MP skill inputs,
resistances and native class/set context. This does not accept a client total,
acquire another SQL generation, persist a cache or publish a notification.
"""
from els_server.domain.native_power_kernel import f32,calculate,STAT_FIELDS,DATA_FIELDS
from els_server.domain import native_option_collector as options
from els_server.domain import native_resonance_attributes as resonance
from els_server.domain import native_cooldown_map as cooldown
from els_server.domain import native_power_normalization as normalization
from els_server.domain import native_condition_contexts as condition_contexts
from els_server.domain import native_conditional_power_attributes as conditional
from els_server.domain import native_max_mp_inputs as mp


def assemble(seven,sources,definitions,*,mode,resonance_level,unit_line,
             resonance_points,resonance_override,resonance_definitions,resonance_pvp_scale,
             condition_resistances,phase_mp_values,unit_mp_values,equipment_mp,
             mp_extension5,mp_extension17,class_kind,unit_factor):
    if type(seven)is not tuple or len(seven)!=7:
        raise ValueError('Seven source-projected native values required')
    seven=tuple(map(f32,seven))
    args=dict(mode=mode,resonance_level=resonance_level,unit_line=unit_line)
    first=options.collect_ordinary(sources,definitions,**args)
    scalars=dict(first['scalars'])
    # Each absent destination here is a zero from the original fresh record,
    # not a missing actor-source assumption. Source acquisition is separate.
    erp,damage,category_cooldown=resonance.apply_resonance(
        {k:scalars.get(k,0.)for k in resonance.FIELDS},resonance_points,resonance_override,
        resonance_definitions,pvp=bool(mode),pvp_scale=resonance_pvp_scale)
    scalars.update(erp)
    initial=dict(damage=damage,alternate={},extended_capabilities={},tags860={},tags870={},resistances=(0,)*7)
    second=options.collect_extended(sources,definitions,initial,**args)
    category_cooldown=cooldown.apply_cooldown_categories(
        {k:scalars.get(k,0.)for k in cooldown.FIELDS},category_cooldown)
    normal=normalization.transform({k:scalars.get(k,0.)for k in normalization.RAW_FIELDS},category_cooldown,{})
    contexts=condition_contexts.build_condition_contexts(condition_resistances,
        physical_defense=seven[5],magical_defense=seven[6],
        physical_defense_rate=first['data'][4],magical_defense_rate=first['data'][5],
        normalized_defense=normal['derived'][0x7e8],normalized_additional=normal['derived'][0x7d8],
        experience_rate=scalars.get(0x1ec,0.),precondition_skill_categories=second['damage'])
    data={k:first['data'][(k-0x6b8)//4]for k in conditional.INTERMEDIATE_DATA}
    # B26830 follows normalization and writes raw attack data separately from
    # scalar leaves. It does not rerun988320 or recalculate the seven vector.
    data,changed=conditional.apply_intermediate(data,
        {k:scalars.get(k,0.)for k in conditional.INTERMEDIATE_SCALARS},first['conditions'],contexts)
    scalars.update(changed)
    maximum=mp.maximum(phase_mp_values,unit_mp_values,worn=equipment_mp,
        flat=f32(first['integer_MP']),rate=first['data'][1],extension5=mp_extension5,extension17=mp_extension17)
    aggregate={k:scalars.get(k,0.)for k in STAT_FIELDS}
    aggregate.update({k:v for k,v in normal['derived'].items()if k in STAT_FIELDS})
    aggregate.update({k:v for k,v in zip(range(0x6d0,0x6ec,4),seven)if k in STAT_FIELDS})
    aggregate[0x614]=first['additional'][1]
    maps={0x5d8:first['capabilities'],0x3f8:first['probability'],0x778:second['damage'],
        0x788:second['alternate'],0x850:second['extended_capabilities'],0x798:normal['map798']}
    arguments=dict(stat_fields=aggregate,data_fields={k:data[k]for k in DATA_FIELDS},maps=maps,
        stat610=first['additional'][0],class_kind=class_kind,max_mp=maximum,unit_factor=unit_factor)
    return dict(power=calculate(**arguments),arguments=arguments,seven=seven,maximum_MP=maximum,
        condition_contexts=contexts,ordinary=first,extended=second)
