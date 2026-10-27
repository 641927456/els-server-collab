"""Offline recomputation path from explicit complete aggregate inputs.

No production registration, persistence or character cache is exposed. The
actor producer must be complete before a gameplay caller can use this path.
"""
from els_server.domain.native_power_normalization import transform
from els_server.domain.native_power_kernel import STAT_FIELDS,MAPS,calculate

DERIVED_POWER_FIELDS=frozenset((0x7b8,0x7bc,0x7c0,0x7c4,0x7d8,0x7dc,
                               0x7e0,0x7e4,0x7e8,0x7fc,0x800))
BASE_POWER_FIELDS=STAT_FIELDS-DERIVED_POWER_FIELDS

def recompute_snapshot(raw,base_fields,data_fields,maps,map7a8,*,stat610,
                       class_kind,max_mp,unit_factor):
    if type(base_fields) is not dict or set(base_fields)!=BASE_POWER_FIELDS:
        raise ValueError('complete base aggregate required; derived fields cannot be supplied')
    if type(maps) is not dict or set(maps)!=MAPS:
        raise ValueError('all six explicit aggregate maps required')
    normalized=transform(raw,maps[0x798],map7a8)
    scalars=dict(base_fields)
    scalars.update({k:v for k,v in normalized['derived'].items() if k in DERIVED_POWER_FIELDS})
    computed_maps=dict(maps);computed_maps[0x798]=normalized['map798']
    result=calculate(scalars,data_fields,computed_maps,stat610=stat610,
                     class_kind=class_kind,max_mp=max_mp,unit_factor=unit_factor)
    return dict(outputs=result,normalized=normalized,scope='offline_complete_aggregate_only')
