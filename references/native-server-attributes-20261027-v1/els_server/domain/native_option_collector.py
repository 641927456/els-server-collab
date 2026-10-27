"""Source-ordered ordinary and extended option passes for native attributes.

Sources must already come from the qualified worn/set/title/companion selectors.
No source is inferred from a previously computed client total. Every pass keeps
duplicates and missing-definition behavior; input dictionaries are never changed.
"""
from dataclasses import dataclass
from els_server.domain.native_power_kernel import f32
from els_server.domain import native_option_scalar_inputs as scalars
from els_server.domain import native_option_scalar_merge as scalar_merge
from els_server.domain import native_option_data_merge as data_merge
from els_server.domain import native_ordinary_option_subset as ordinary
from els_server.domain import native_ordinary_option_power_maps as power_maps
from els_server.domain import native_option_power_maps as map_inputs
from els_server.domain import native_option_condition_inputs as condition_inputs
from els_server.domain import native_option_max_mp as mp
from els_server.domain import native_extended_option_inputs as extended_inputs
from els_server.domain import native_extended_option_maps as extended_maps
from els_server.domain import native_option_factor_inputs as factor_inputs


@dataclass(frozen=True)
class OptionSource:
    option_ids: tuple
    level: int
    condition_value: int
    rank_factor: float
    weight: float


def collect(sources,definitions,*,mode,resonance_level,unit_line):
    if type(sources)is not tuple or len(sources)>512:
        raise ValueError('Complete bounded ordered option sources required')
    if type(definitions)is not dict or len(definitions)>100000:
        raise ValueError('Current complete option definition index required')
    if type(mode)is not int or mode not in(0,1):
        raise ValueError('Explicit native phase mode required')
    if type(resonance_level)is not int or not -2**31<=resonance_level<2**31:
        raise ValueError('Original signed resonance level required')
    if type(unit_line)is not int or not -2**31<=unit_line<2**31:
        raise ValueError('Original signed class branch required')
    for source in sources:
        if type(source)is not OptionSource or type(source.option_ids)is not tuple or len(source.option_ids)>16384:
            raise ValueError('Qualified native option source required')
        if type(source.level)is not int or not 0<=source.level<=255:
            raise ValueError('Original byte source level required')
        for value in(source.condition_value,*source.option_ids):
            if type(value)is not int or not -2**31<=value<2**31:
                raise ValueError('Original signed option identity/condition required')
        f32(source.rank_factor);f32(source.weight)
    fields=dict.fromkeys(scalar_merge.FIELDS,0.);data=(0.,)*13
    capabilities={};probability={};additional=(0,0.);conditions=();integer_mp=0
    for source in sources:
        args=dict(mode=mode,resonance_level=resonance_level,unit_line=unit_line,
            condition_value=source.condition_value,rank_factor=source.rank_factor,weight=source.weight)
        for identity in source.option_ids:
            definition=definitions.get(identity)
            if definition is None:continue
            metadata=ordinary.metadata(definition);values=scalars.scalar_inputs(definition)
            incoming=tuple(values[k]for k in(0x6b8,0x6bc,0x6c0,0x6c4,0x6c8,0x6cc))+data_merge.direct_option_stats(definition.get('STAT',{}))
            fields,data=ordinary.merge(fields,{k:values[k]for k in scalar_merge.FIELDS},data,incoming,
                metadata,level=source.level,**args)
            capabilities,probability,additional,conditions=power_maps.merge(capabilities,probability,
                additional,conditions,map_inputs.source_map_inputs(definition),
                condition_inputs.condition_input(definition),metadata,**args)
            integer_mp=mp.merge(integer_mp,mp.source_value(definition),metadata,mode=mode,
                resonance_level=resonance_level,unit_line=unit_line,rank_factor=source.rank_factor,weight=source.weight)
    # Whole897100's cap follows all first-pass source callbacks.
    fields[0x20]=min(fields[0x20],40.)
    damage={};alternate={};extended_capabilities={};tags860={};tags870={};resistances=(0,)*7
    for source in sources:
        for identity in source.option_ids:
            definition=definitions.get(identity)
            if definition is None:continue
            metadata=ordinary.metadata(definition)
            if not ordinary.ordinary_entry(metadata,resonance_level=resonance_level,mode=mode):continue
            values=scalars.scalar_inputs(definition)
            damage,alternate,extended_capabilities,tags860,tags870,resistances=extended_maps.merge_extended_maps(
                damage,alternate,extended_capabilities,tags860,tags870,resistances,
                **extended_inputs.extended_source_inputs(definition),
                category_rates=tuple(values[k]for k in(0x3e8,0x3ec,0x3f0,0x3f4)),
                factor_rows=factor_inputs.capability_rows(definition),weight=source.weight)
    return dict(scalars=fields,data=data,capabilities=capabilities,probability=probability,
        additional=additional,conditions=conditions,integer_MP=integer_mp,damage=damage,alternate=alternate,
        extended_capabilities=extended_capabilities,tags860=tags860,tags870=tags870,resistances=resistances)
