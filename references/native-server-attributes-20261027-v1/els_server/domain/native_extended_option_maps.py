"""Original9873F0/B23F70 second-pass option maps and integer resistances.

Input rows still require the original caller's ownership/activation checks.
The callback weight is distinct from the earlier scalar-merge weight.
"""
from els_server.domain.native_power_kernel import f32

CAPABILITY_FIELDS=frozenset(range(0x598,0x5c8,4))
CAPABILITY_TYPES={
    770:(0x598,501),771:(0x59c,502),772:(0x5a0,503),
    773:(0x5a4,504),774:(0x5b0,505),775:(0x5b8,509),
    776:(0x5c4,512),777:(0x5bc,510),778:(0x5ac,506),
    1675:(0x5b4,508),1676:(0x5a8,507),2267:(0x5c0,511),
    2976:(0x598,501),2977:(0x59c,502),
}
CAPABILITY_EPSILON=f32(1.1920928955078125e-7)


def integer(value):
    if type(value)is not int or not -2**31<=value<2**31:
        raise ValueError('Explicit signed native integer required')
    return value


def vector(values):
    if type(values)is not tuple or len(values)>16384:
        raise ValueError('Bounded complete ordered source vector required')
    return tuple(integer(v)for v in values)


def float_map(values):
    if type(values)is not dict or len(values)>2048:
        raise ValueError('Complete native category map required')
    return {integer(k):f32(v)for k,v in values.items()}


def merge_extended_maps(damage,alternate,capabilities,tags860,tags870,resistances,
                        *,skills,skill_rate,alternate_skills,alternate_rate,
                        category_rates,source_resistances,capability_fields,
                        factor_rows,weight):
    damage=float_map(damage);alternate=float_map(alternate)
    if type(capabilities)is not dict or len(capabilities)>2048:
        raise ValueError('Complete native pair map required')
    pairs={}
    for key,value in capabilities.items():
        if type(key)is not tuple or len(key)!=2 or type(key[1])is not int or key[1]not in(0,1):
            raise ValueError('Native capability pair key required')
        pairs[(integer(key[0]),key[1])]=f32(value)
    def tags(values):
        if type(values)is not dict or len(values)>2048:
            raise ValueError('Complete native capability tag map required')
        return {integer(k):set(vector(v))for k,v in values.items()}
    tags860=tags(tags860);tags870=tags(tags870)
    if type(category_rates)is not tuple or len(category_rates)!=4:
        raise ValueError('All four original category rates required')
    if type(capability_fields)is not dict or set(capability_fields)!=CAPABILITY_FIELDS:
        raise ValueError('All twelve original capability coefficients required')
    capability_fields={k:f32(v)for k,v in capability_fields.items()}
    before=vector(resistances);source=vector(source_resistances)
    if len(before)!=7 or len(source)!=7:
        raise ValueError('All seven original resistance words required')
    weight=f32(weight);temporary={}
    def add(values,key,value):
        values[key]=f32(values[key]+value)if key in values else value
    rate=f32(skill_rate)
    for skill in vector(skills):
        if rate!=0.:add(temporary,skill,f32(rate*weight))
    for category,raw in zip((6,14,15,16),category_rates):
        rate=f32(raw)
        if rate!=0.:
            # Original987360 applies the callback factor again. Preserve
            # both rounded multiplies rather than simplifying to one scale.
            add(temporary,category,f32(f32(rate*weight)*weight))
    for key in sorted(temporary):add(damage,key,temporary[key])
    temporary={};rate=f32(alternate_rate)
    for skill in vector(alternate_skills):
        if rate!=0.:add(temporary,skill,f32(rate*weight))
    for key in sorted(temporary):add(alternate,key,temporary[key])
    resistance=[]
    for a,b in zip(before,source):
        value=f32(f32(f32(b)*weight)+f32(a))
        resistance.append(int(value)if -2**31<=value<2**31 else -2**31)
    if type(factor_rows)is not tuple or len(factor_rows)>16384:
        raise ValueError('Complete original factor rows required')
    for kind,addition in factor_rows:
        kind=integer(kind);flag=int(f32(addition)>0.)
        if kind==2095:
            for key in(501,502):tags870.setdefault(key,set()).add(kind)
        elif 2179<=kind<=2188:tags860.setdefault(501,set()).add(kind)
        elif 2189<=kind<=2198:tags860.setdefault(502,set()).add(kind)
        elif 2209<=kind<=2218:tags860.setdefault(513,set()).add(kind)
        elif 2219<=kind<=2228:
            for key in(503,504):tags860.setdefault(key,set()).add(kind)
        elif kind in CAPABILITY_TYPES:
            offset,key=CAPABILITY_TYPES[kind];coefficient=capability_fields[offset]
            if abs(coefficient)>CAPABILITY_EPSILON:
                value=f32(coefficient*weight);pair=(key,flag)
                old=pairs.setdefault(pair,0.)
                pairs[pair]=f32(value+old)if flag else value if value>old else old
    return (damage,alternate,pairs,
        {k:tuple(sorted(v))for k,v in tags860.items()},
        {k:tuple(sorted(v))for k,v in tags870.items()},tuple(resistance))
