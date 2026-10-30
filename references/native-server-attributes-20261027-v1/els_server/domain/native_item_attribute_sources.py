"""Canonical item option sources including the wrapper's extra circuit pass."""
import struct
from els_server.domain.native_dynamic_sets import property_value
from els_server.domain.native_item_attribute_options import collect,template_level
from els_server.domain.native_option_collector import OptionSource
from els_server.domain.native_circuit_attribute_inputs import collect as circuit_options


def callbacks(row,record,*,character_level,category77,activation,circuit_state,rank_factor):
    if (type(record)is not bytes or len(record)!=232
            or struct.unpack_from('<I',record)[0]!=row['template_id']
            or struct.unpack_from('<I',record,4)[0]!=row['flags4']):
        raise ValueError('Bound current item record required')
    if type(category77)is not bool or type(activation)is not dict or set(activation)!={0x4a,0x4e,0x50}:
        raise ValueError('Qualified original resource/armor activation required')
    if any(type(v)is not bool for v in activation.values()):
        raise ValueError('Original activation predicates required')
    options,level=collect(row['option_vectors'],row['properties'],row['template_options'],
        character_level=character_level,template_level=template_level(record),
        allow26=activation[0x4a],allow27=activation[0x4e],circuit_state=circuit_state)
    condition=(property_value(row['properties'],0x28)or 7)if row['flags4']&0x80 else 7 if category77 else row['native18']
    result=[OptionSource(options,level,condition,rank_factor,1.)]
    # 897290/889A20 run the ordinary vector first, then the separate weighted
    # circuit vector. A uniform weight per one-ID source preserves that order
    # in both portable passes without adding any circuit ID to naked input.
    if activation[0x50]and any(p[0]==0x50 for p in row['properties']):
        result.extend(OptionSource((identity,),level,condition,rank_factor,weight)
            for identity,weight in circuit_options(row['template_id'],row['option_vectors'][0x2d8]))
    return tuple(result)
