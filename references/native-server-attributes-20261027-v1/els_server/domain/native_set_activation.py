"""198A0A0 registration phase AFTER867440 candidate qualification.

Do not use this phase alone as complete equipment eligibility. Duplicate
registration rows consume slots exactly as the source does; empty effects do
not. The third registration field is opaque and preserved, not interpreted.
"""
from els_server.domain.native_set_conditions import uint32,select_effect_ids

def registration_present(registrations,preset,set_id):
    """867440 early activation-required gate deliberately does not filter side."""
    return any(row[0]==preset and row[3]==set_id for row in registrations)

def activation_phase(registrations,preset,selector,candidates,definitions):
    uint32(preset);uint32(selector)
    if preset>65535:raise ValueError('uint16 current preset required')
    for row in registrations:
        if type(row) is not tuple or len(row)!=4:raise ValueError('four registration words required')
        for v in row:uint32(v)
    remaining=dict(candidates);accepted=[];removed=[]
    for key,pair in remaining.items():
        uint32(key)
        if type(pair) is not tuple or len(pair)!=2:raise ValueError('qualifier and count required')
        for value in pair:uint32(value)
    for row in registrations:
        rp,side,opaque,key=row
        if not key or side!=selector or rp!=preset or key not in remaining:continue
        definition=definitions.get(key)
        if definition is None or not definition['activation_required']:continue
        if len(accepted)>=3:
            del remaining[key];removed.append(key);continue
        qualifier,pieces=remaining[key]
        effects=select_effect_ids(definition['ordinary'],definition['qualified'],qualifier,pieces)
        if effects:accepted.append(row+(pieces,))
    return dict(candidates=remaining,activated=tuple(accepted),removed=tuple(removed))
