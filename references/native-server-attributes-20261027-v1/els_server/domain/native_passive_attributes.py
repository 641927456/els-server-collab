"""Original 8978C0 scalar phase from explicit owned skill/context inputs.

All percentages use the immutable, pre-passive stat vector. Native source order,
the defense cross-field operations and the fixed 28434 rank argument remain.
This phase does not infer ownership, equipped bonus levels or skill selection.
"""
import math
import struct


def f32(value):
    if type(value) not in (int,float) or not math.isfinite(value):
        raise ValueError('Finite native passive value required')
    try:
        result=struct.unpack('<f',struct.pack('<f',value))[0]
    except (OverflowError,struct.error) as error:
        raise ValueError('Native passive float32 bound') from error
    if not math.isfinite(result):
        raise ValueError('Native passive float32 overflow')
    return result


def vector(value):
    if type(value) is not dict or value.get('0','absent') is not None:
        raise ValueError('Explicit original one-based skill vector required')
    keys=set(value)-{'0'}
    if keys!={str(n) for n in range(1,len(keys)+1)}:
        raise ValueError('Contiguous original skill vector required')
    return tuple(f32(value[str(n)]) for n in range(1,len(keys)+1))


def parameter(definition,name,rank,*,pvp,direct,default):
    """9C5A10/98D760 named-row order and direct-vector fallback semantics."""
    if type(rank) is not int or not -(1<<31)<=rank<(1<<31) or type(pvp) is not bool:
        raise ValueError('Explicit native rank and context required')
    keys=[key for key in definition if key.startswith('NUMERICAL_DATA')]
    if set(keys)!={'NUMERICAL_DATA'+str(n) for n in range(1,len(keys)+1)}:
        raise ValueError('Contiguous original numerical rows required')
    for n in range(1,len(keys)+1):
        row=definition['NUMERICAL_DATA'+str(n)]
        if row.get('m_wstrName')!=name:
            continue
        # Original 9AF591..9AF759 uses the same float-vector producer for
        # both display formats, including fractional values in format "i".
        if row.get('m_ParamType') not in('f','i'):
            raise ValueError('Native float parameter source required')
        values=vector(row.get('m_Value',{'0':None}))
        if not values:
            return f32(0.)
        index=rank-1
        if not 0<=index<len(values):
            index=len(values)-1
        result=values[index]
        if pvp:
            rates=vector(row.get('m_Pvp_Rate',{'0':None}))
            result=f32(result*(rates[min(index,len(rates)-1)] if rates else f32(1.)))
        return result
    if direct:
        values=vector(definition.get(name,{'0':None}))
        if 1<=rank<=len(values):
            return values[rank-1]
    return f32(default)


def apply(base,query_ranks,definitions,unit_selections,rules,*,phase_pvp,unit_pvp,
          flat_attack,flat_defense):
    """Pure arithmetic; all selected levels/definitions must be server-owned."""
    if type(base) is not tuple or len(base)!=7:
        raise ValueError('Explicit seven-field passive basis required')
    if type(phase_pvp) is not bool or type(unit_pvp) is not bool:
        raise ValueError('Explicit passive mode contexts required')
    original=list(f32(value) for value in base)
    for index,value in ((1,flat_attack),(2,flat_attack),(5,flat_defense),(6,flat_defense)):
        original[index]=f32(original[index]+f32(value))
    out=list(original)
    for rule in rules:
        sid=rule['skill']
        rank=query_ranks.get(sid,0)
        if type(rank) is not int or not 0<=rank<=255:
            raise ValueError('Native queried passive rank required')
        if not rank:
            continue
        definition=definitions[sid]
        if definition.get('m_eID')!=sid:
            raise ValueError('Native passive definition identity mismatch')
        for operation in rule['operations']:
            target,basis=operation['target'],operation['basis']
            if target not in(1,2,5,6) or basis not in(1,2,5,6):
                raise ValueError('Unexpected native passive scalar field')
            reader=operation['reader']
            selected=definition
            level=operation.get('rank_override',rank)
            if reader=='unit':
                # 8903F0 resolves changed/default/equipped skill identities
                # before reading parameters. Never assume the queried ID wins.
                selected_id,level=unit_selections[sid]
                selected=definitions[selected_id]
                if selected.get('m_eID')!=selected_id:
                    raise ValueError('Native selected skill identity mismatch')
            mode=unit_pvp if reader=='unit' else False if reader=='raw_named'else phase_pvp if reader!='direct' or operation.get('phase_pvp')else False
            value=parameter(selected,operation['parameter'],level,pvp=mode,
                            direct=reader=='direct',default=operation['default'])
            if operation.get('negate'):
                value=-value
            transform=operation['transform']
            if transform=='ratio':
                value=f32(value-f32(1.))
            elif transform=='percent':
                value=f32(value*.01) if operation['scale_precision']=='double_then_float' else f32(value*f32(.01))
            elif transform!='identity':
                raise ValueError('Unexpected native passive transform')
            delta=f32(value*original[basis])
            if operation['operation']=='add':
                out[target]=f32(out[target]+delta)
            elif operation['operation']=='assign':
                out[target]=delta
            else:
                raise ValueError('Unexpected native passive operation')
    return tuple(out)


def apply_naked(base,query_ranks,definitions,*,pvp,extension5,extension16):
    """861940 naked source phase, before equipment/set/ordinary contributions."""
    if type(base) is not tuple or len(base)!=7 or type(pvp) is not bool:
        raise ValueError('Explicit native naked source/context required')
    original=tuple(f32(v)for v in base)
    out=list(original)
    for sid in(106,21403,26403,7407,900401,900412):
        rank=query_ranks.get(sid,0)
        if type(rank)is not int or not 0<=rank<=255:
            raise ValueError('Native queried naked skill rank required')
    # Exact current-image 43707E0 (95 BF 56 33), not zero. Omitting this
    # native epsilon changes some HP/defense results by one float32 ULP.
    epsilon=struct.unpack('<f',bytes.fromhex('95bf5633'))[0]
    def read(sid,key,mode=False):
        rank=query_ranks[sid]
        definition=definitions[sid]
        if definition.get('m_eID')!=sid:
            raise ValueError('Native naked skill identity mismatch')
        return parameter(definition,key,rank,pvp=mode,direct=True,default=0.)
    if query_ranks.get(21403,0):
        ratio=f32(f32(read(21403,'SA_MAX_HP_REL',pvp)*f32(.01))+f32(1.))
        out[0]=f32(ratio*out[0])
    if query_ranks.get(26403,0):
        delta=f32(f32(read(26403,'SA_MAX_HP_REL')*original[0])*f32(.01))
        out[0]=f32(out[0]+delta)
    if query_ranks.get(7407,0):
        for index,key in((5,'SA_DEF_PHYSIC_REL'),(6,'SA_DEF_MAGIC_REL'),(0,'SA_MAX_HP_REL')):
            delta=f32(f32(f32(read(7407,key)-f32(1.))+epsilon)*original[index])
            out[index]=f32(out[index]+delta)
    if query_ranks.get(106,0):
        delta=f32(f32(f32(read(106,'SA_MAX_HP_REL')-f32(1.))+epsilon)*original[0])
        out[0]=f32(out[0]+delta)
    for sid in(900401,900412):
        if query_ranks.get(sid,0):
            out[0]=f32(out[0]+read(sid,'SA_MAX_HP_ABS',pvp))
    delta=f32(f32(f32(f32(extension16)+f32(extension5))*original[0])*f32(.01))
    out[0]=f32(out[0]+delta)
    return tuple(out)
