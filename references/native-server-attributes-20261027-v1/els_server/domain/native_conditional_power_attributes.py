"""Original B26140 condition-vector phase from explicit owned context.

Context offsets retain native names until their authoritative producer is
qualified. No missing context is substituted with zero or client totals.
"""
import math
from els_server.domain.native_power_kernel import f32

FIELDS=frozenset((0x6c0,0x6c4,0x41c,0x1ec,0xf8,0xf4))
CONTEXTS=frozenset((0x3060,0x3064,0x3068,0x306c,0x3070,0x3078))
EPSILON=f32(1.1920928955078125e-7)  # original43707E4
ATTACK=(0x6c0,0x6c4)
RULES={1:(0x3060,(0x41c,)),3:(0x3068,ATTACK),4:(0x3068,(0x41c,)),
       5:(0x3068,(0x1ec,)),6:(0x3068,(0xf8,)),7:(0x3068,(0xf4,)),
       8:(0x3078,ATTACK),9:(0x3078,(0x41c,)),10:(0x3078,(0x1ec,)),
       11:(0x3078,(0xf8,)),12:(0x3078,(0xf4,)),13:(0x306c,ATTACK),
       14:(0x306c,(0x41c,)),15:(0x306c,(0x1ec,)),16:(0x306c,(0xf8,)),
       17:(0x306c,(0xf4,)),18:(0x3060,ATTACK),19:(0x3060,(0x1ec,)),
       20:(0x3060,(0xf8,)),21:(0x3060,(0xf4,)),22:(0x3070,ATTACK),
       23:(0x3070,(0x41c,)),24:(0x3070,(0xf8,)),25:(0x3070,(0xf4,))}


def apply(fields, conditions, contexts):
    if type(fields)is not dict or set(fields)!=FIELDS:
        raise ValueError('Complete original conditional scalar fields required')
    if type(contexts)is not dict or set(contexts)!=CONTEXTS:
        raise ValueError('Complete original conditional source context required')
    if type(conditions)is not tuple or len(conditions)>1024:
        raise ValueError('Bounded original condition-vector required')
    out={key:f32(value)for key,value in fields.items()}
    source={key:f32(value)for key,value in contexts.items()}
    for row in conditions:
        if type(row)is not tuple or len(row)!=4 or type(row[0])is not int or not 0<=row[0]<2**32:
            raise ValueError('Original condition type/u32 and three floats required')
        kind=row[0];threshold,value,cap=map(f32,row[1:])
        if kind==2:
            # Current finite source domain. A zero divisor requires its own
            # native nonfinite behavior qualification, never guessed handling.
            if threshold<=0:raise ValueError('Positive original step divisor required')
            current=source[0x3064]
            if current<=threshold and abs(f32(current-threshold))>EPSILON:continue
            ratio=f32(current/threshold)
            value=min(cap,f32(f32(math.floor(ratio))*value))
            targets=ATTACK
        else:
            rule=RULES.get(kind)
            if rule is None:continue  # Original switch ignores unknown types.
            context,targets=rule;current=source[context]
            if current<=threshold and abs(f32(current-threshold))>EPSILON:continue
            if targets==(0xf4,):value=f32(value*f32(100.))
        for target in targets:out[target]=f32(value+out[target])
    return out


INTERMEDIATE_DATA=frozenset((0x6b8,0x6c0,0x6c4,0x6c8,0x6cc))
INTERMEDIATE_SCALARS=FIELDS-set(ATTACK)


def apply_intermediate(data_fields, scalar_fields, conditions, contexts):
    """B26830 writes raw attack data separately from extended scalar fields.

    It leaves existing normalized derived values unchanged, exactly as the
    original intermediate phase. Applying it to a single raw record changes
    which values89B430 subsequently reads.
    """
    if type(data_fields)is not dict or set(data_fields)!=INTERMEDIATE_DATA:
        raise ValueError('Complete original intermediate data inputs required')
    if type(scalar_fields)is not dict or set(scalar_fields)!=INTERMEDIATE_SCALARS:
        raise ValueError('Complete original intermediate scalar inputs required')
    data={key:f32(value)for key,value in data_fields.items()}
    scalars={key:f32(value)for key,value in scalar_fields.items()}
    combined=dict(scalars);combined.update({key:data[key]for key in ATTACK})
    changed=apply(combined,conditions,contexts)
    data.update({key:changed[key]for key in ATTACK})
    scalars.update({key:changed[key]for key in INTERMEDIATE_SCALARS})
    return data,scalars
