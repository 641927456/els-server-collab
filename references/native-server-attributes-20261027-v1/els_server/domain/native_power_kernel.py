"""Offline candidate for dx11_260923 original89B430 and its three math helpers.

Consumes a COMPLETE already-built stat aggregate. This does not build actor,
equipment, set or passive effects, accept client-reported power, store a value,
or refresh the wire cache. No production handler imports this isolated module.
"""
import math
import struct

IMAGE_SHA256='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
FULL_ACTOR_INPUTS_VERIFIED=False
STAT_FIELDS=frozenset((0xf8,0x11c,0x368,0x370,0x41c,0x448,0x4f4,0x558,0x560,0x564,0x568,0x56c,0x570,0x574,0x578,0x57c,0x580,0x584,0x588,0x58c,0x590,0x594,0x5e8,0x5ec,0x614,0x61c,0x6d0,0x6d4,0x6d8,0x6e4,0x6e8,0x7b8,0x7bc,0x7c0,0x7c4,0x7d8,0x7dc,0x7e0,0x7e4,0x7e8,0x7fc,0x800))
DATA_FIELDS=frozenset((0x6b8,0x6c0,0x6c4,0x6c8,0x6cc))
MAPS=frozenset((0x5d8,0x850,0x778,0x788,0x798,0x3f8))

def f32(value):
    if type(value) not in (int,float) or not math.isfinite(value):raise ValueError('Finite numeric input required')
    try:result=struct.unpack('<f',struct.pack('<f',value))[0]
    except (OverflowError,struct.error) as e:raise ValueError('Float32 input range') from e
    if not math.isfinite(result):raise ValueError('Finite float32 input required')
    return result

def _add(*values):
    result=values[0]
    for value in values[1:]:result=f32(result+value)
    return result

def _weighted(values,weights):
    top=sorted((f32(a*f32(b)) for a,b in zip(values,weights)),reverse=True)[:2]
    return _add(f32(top[0]*f32(.7)),f32(top[1]*f32(.3)))

def calculate(stat_fields,data_fields,maps,*,stat610,class_kind,max_mp,unit_factor):
    """Return the original two float32 outputs, without assigning gameplay names.

    Exact scalar and map groups are required. Empty maps are explicit, never
    substituted for missing groups. Values outside this finite calculation
    domain raise rather than become a plausible zero or fabricated power.
    """
    if set(stat_fields)!=STAT_FIELDS or set(data_fields)!=DATA_FIELDS or set(maps)!=MAPS:
        raise ValueError('Incomplete or unknown kernel input fields')
    s={k:f32(v) for k,v in stat_fields.items()};d={k:f32(v) for k,v in data_fields.items()}
    if type(stat610) is not int or not -2**31<=stat610<2**31:raise ValueError('Stat610 int32')
    if class_kind is not None and (type(class_kind) is not int or not -2**31<=class_kind<2**31):raise ValueError('Class kind int32 or missing')
    if type(unit_factor) not in (int,float) or not math.isfinite(unit_factor):raise ValueError('Unit factor finite double')
    mp=f32(max_mp);m={};count=0
    for off,values in maps.items():
        if type(values) is not dict or len(values)>1024:raise ValueError('Bounded explicit map required')
        count+=len(values);rows={}
        for key,value in values.items():
            if off in (0x850,0x3f8):
                if type(key) is not tuple or len(key)!=2 or type(key[0]) is not int or type(key[1]) is not int or key[1] not in (0,1):raise ValueError('Pair map key')
                number=key[0]
            else:
                if type(key) is not int:raise ValueError('Integer map key')
                number=key
            if not -2**31<=number<2**31:raise ValueError('Map key int32')
            if off==0x3f8:
                if not 0<=number<=100:raise ValueError('Damage probability row')
                rows[key]=f32(value)
            else:rows[key]=f32(value)
        m[off]=rows
    if count>2048:raise ValueError('Total map bound')
    get=lambda off,key:m[off].get(key,0.)
    # OriginalB24430 is called with its float argument zero by89B430, so its
    # nonzero-argument Lua branches do not participate in this kernel.
    def bonus(key):return max(get(0x5d8,key),get(0x850,(key,0)),get(0x850,(key,1)))
    scale=lambda key:_add(get(0x5d8,key),1.)
    def attack(base,relative,data,key,scale_key):
        value=f32(_add(f32(s[base]*_add(bonus(key),s[relative],d[data])),s[base])*scale(scale_key))
        if not -2**31<=value<2**31:raise ValueError('Original signed conversion outside finite domain')
        return int(value)
    atk=max(attack(0x6d4,0x560,0x6c0,0x1f5,3),attack(0x6d8,0x564,0x6c4,0x1f6,4))
    critical=float(f32(_add(bonus(0x1f9),s[0x7b8],s[0x57c])*scale(0x65)))
    if critical<=0:critical=0.
    critical=(float(_add(bonus(0x1fb),s[0x580],s[0xf8]))+.5)*critical+1.
    common=_add(s[0x588],s[0x558],s[0x61c]);keys=(6,14,15,16,13)
    helper_a=_weighted([_add(s[0x594],s[0x11c])]+[_add(get(0x778,k),get(0x788,k)) for k in keys],[.1,.3,.8,1,1,.5])
    helper_b=_weighted([_add(common,get(0x798,k)) if k!=13 else get(0x798,k) for k in keys],[.3,.8,1,1,.5])
    class_factor=0.
    if class_kind is None or class_kind==0:class_factor=max(s[0x7c0],s[0x7c4])*.4+1.
    elif class_kind==1:class_factor=s[0x7c0]*.4+1.
    elif class_kind==2:class_factor=s[0x7c4]*.4+1.
    damage=0.
    for (probability,flag),value in sorted(m[0x3f8].items()):
        p=probability if flag==1 else 100-probability
        damage=_add(damage,f32(f32(f32(p)*f32(.01))*value))
    if stat610>0 and s[0x614]>0:damage=_add(damage,f32(f32(f32(stat610)*f32(.01))*s[0x614]))
    speed_den=(1.-float(s[0x7e0]))*300.
    global_factor=float(_add(s[0x800],1.,s[0x5e8],s[0x4f4],s[0x5ec]))
    defence=f32(_add(f32(s[0x6e8]*_add(bonus(0x1f8),s[0x56c],d[0x6cc])),s[0x6e8],f32(s[0x6e4]*_add(bonus(0x1f7),s[0x568],d[0x6c8])),s[0x6e4])*.5)
    defence=_add(defence,f32(4154.3))
    hp=float(_add(min(f32(s[0x6d0]*.5),d[0x6b8]),s[0x6d0]))*1.4000000192027073e-05
    cooldown_den=f32(1.-_add(bonus(0x200),s[0x7e8],s[0x590]))
    reduction_den=f32(1.-f32(s[0x7dc]*f32(.4)))
    auxiliary=float(_add(s[0x7fc],s[0x58c]))+1.
    if min(abs(speed_den),abs(cooldown_den),abs(reduction_den),abs(auxiliary))==0:raise ValueError('Singular original kernel denominator')
    result_a=(((s[0x370]*.7+1.)*(float(_add(bonus(0x1fa),s[0x7bc],s[0x578]))*.5*float(scale(0x67))+1.)*auxiliary*(helper_a+1.)*(float(_add(bonus(0x1fc),s[0x584],s[0x41c]))+1.)*(damage+1.)+float(_add(bonus(0x1fd),s[0x7d8],s[0x574]))*.5)*(atk*.05700000002980232)*critical*class_factor*(float(_add(bonus(0x1fe),s[0x7e4],s[0x570]))*.25*float(scale(0x12d))+1.)*(((float(mp)-300.)*.1)/speed_den+1.)*float(_add(helper_b,1.))*global_factor*(s[0x448]+1.)*unit_factor)
    result_b=((((hp*global_factor*float(defence))/float(cooldown_den))/float(reduction_den))/auxiliary)*float(_add(f32(min(s[0x368],1.)*.25),1.))
    result=(f32(result_a),f32(result_b))
    if min(result)<0:raise ValueError('Negative kernel output outside accepted domain')
    return result
