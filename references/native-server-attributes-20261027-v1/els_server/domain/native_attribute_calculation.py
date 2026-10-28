"""Compute final seven/MP/power from one complete qualified source generation.

This joins the source phases; ownership, mutable Unit context, expiration and
notification timing belong to the snapshot/lifecycle caller. It never accepts a
client combat total, holds a SQL transaction or writes a player cache.
"""
from els_server.domain import native_option_collector as options
from els_server.domain import native_attribute_projection as projection
from els_server.domain import native_power_aggregation as power


def calculate(base,equipped_flat,learned_flat,query_ranks,skill_definitions,
              unit_selections,rules,sources,option_definitions,*,mode,unit_pvp,
              title_direct,naked_extension5,naked_extension16,
              flat_attack_extension,flat_defense_extension,
              resonance_level,unit_line,power_context):
    first=options.collect_ordinary(sources,option_definitions,mode=mode,
        resonance_level=resonance_level,unit_line=unit_line)
    seven=projection.compose(base,equipped_flat,tuple(first['data'][6:]),learned_flat,
        query_ranks,skill_definitions,unit_selections,rules,phase_pvp=bool(mode),unit_pvp=unit_pvp,
        naked_extension5=naked_extension5,naked_extension16=naked_extension16,
        flat_attack_extension=flat_attack_extension,flat_defense_extension=flat_defense_extension,
        extra_hp=first['fixed_HP'],title_direct=title_direct)
    if type(power_context)is not dict:
        raise ValueError('Complete qualified native power context required')
    result=power.assemble(seven,sources,option_definitions,mode=mode,
        resonance_level=resonance_level,unit_line=unit_line,**power_context)
    return dict(result,first_source_record=first)
