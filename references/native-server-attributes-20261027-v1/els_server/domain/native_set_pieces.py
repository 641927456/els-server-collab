"""867440 piece aggregation with explicit qualified category option inputs after explicit worn collection.

Set IDs must come from the qualified6CAB20 phase. Category-specific color and
activation ownership producers remain separate inputs; no actual actor exists
merely because these explicit vectors and registration controls are supplied.
"""
from els_server.domain.native_set_activation import activation_phase,registration_present
from els_server.domain.native_item_set_qualifiers import qualifies

def collect(main,secondary,definitions,registrations,*,preset,selector,main_overrides,
            fashion_overrides,include_bit7,profile_level,force900404):
    if type(main)is not tuple or type(secondary)is not tuple:raise ValueError('explicit qualified item vectors required')
    if type(include_bit7)is not bool or type(force900404)is not bool:raise ValueError('explicit flags and Force ownership required')
    counts={}
    def add(row,overrides):
        sid=row['resolved_set_id']
        qualifier=overrides.get((sid,selector),row['flags4']>>20&15)
        old=counts.get(sid)
        counts[sid]=(old[0],old[1]+1)if old else(qualifier,1)
    for row in main:
        if row['flags4']&0x80 and not include_bit7:continue
        sid=row['resolved_set_id'];definition=definitions.get(sid)
        if not sid or definition is None:continue
        if definition['activation_required']and not registration_present(registrations,preset,sid):continue
        if not qualifies(row,definition['category']):continue
        add(row,main_overrides)
    result=activation_phase(registrations,preset,selector,counts,definitions)
    counts=result['candidates']
    if profile_level>3:
        for row in secondary:
            if row['resolved_set_id']:add(row,fashion_overrides)
    if force900404:
        counts={sid:(qualifier,count+int(count>2))for sid,(qualifier,count)in counts.items()}
    return counts
