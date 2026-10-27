"""8967F0 -> 895580 -> D36B20, with explicit runtime table inputs.

This covers the extension point contributor, not every learned passive or set.
The resource loader and all learned-skill effect evaluators remain separate.
"""
from els_server.domain.native_power_kernel import f32

def i32(value):
    if type(value) is not int or not -2**31<=value<2**31:
        raise ValueError('signed int32 required')
    return value

def contribution(points,override,definitions,stat_id,original_arg,scale):
    i32(stat_id)
    if type(original_arg) is not int or original_arg not in (0,1):
        raise ValueError('reviewed boolean argument required')
    scale=f32(scale)
    if type(points) is not dict or len(points)>1024:
        raise ValueError('bounded explicit point map required')
    for key,value in points.items():i32(key);i32(value)
    if type(override) is not tuple or len(override)!=2:
        raise ValueError('explicit override pair required')
    i32(override[0]);i32(override[1])
    if definitions is None:return 0.  # Explicit absent original manager.
    if type(definitions) is not dict or len(definitions)>1024:
        raise ValueError('bounded explicit extension definition map required')
    for key,row in definitions.items():
        i32(key)
        if type(row) is not tuple or len(row)!=3:raise ValueError('coefficient, cap16, exclusion8 required')
        f32(row[0])
        if type(row[1]) is not int or not 0<=row[1]<=65535:raise ValueError('uint16 cap required')
        if type(row[2]) is not int or not 0<=row[2]<=255:raise ValueError('uint8 exclusion required')
    count=points.get(stat_id,0)
    if stat_id in points and stat_id==override[0]:
        count=((count+override[1]+2**31)%2**32)-2**31
    row=definitions.get(stat_id)
    if row is None:return 0.
    coefficient,cap,exclusion=row
    if cap and count>=cap:count=cap
    if (original_arg^1) and exclusion:return 0.
    value=f32(f32(count)*f32(coefficient))
    return f32(value*(scale if original_arg==0 else 1.))
