"""Original988D70 transformation of the qualified scalar/data subset.

This is the pre-merge source copy. Its coefficient differs from callback
weight and PvP rate. Container members outside this subset stay separate.
"""
from els_server.domain.native_power_kernel import f32
from els_server.domain.native_option_scalar_merge import FIELDS

COPIED=frozenset((0x11c,0x4f0,0x4f4,0x5e8,0x5ec,0x61c))


def transform(scalars,data,coefficient):
    if type(scalars)is not dict or set(scalars)!=FIELDS:
        raise ValueError('Complete qualified pre-merge scalar subset required')
    if type(data)is not tuple or len(data)!=13:
        raise ValueError('Complete original six-plus-seven data required')
    coefficient=f32(coefficient)
    return ({k:f32(v)if k in COPIED else f32(coefficient*f32(v))
             for k,v in scalars.items()},tuple(f32(coefficient*f32(v))for v in data))
