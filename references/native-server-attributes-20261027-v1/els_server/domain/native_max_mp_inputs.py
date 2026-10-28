"""Original895790 MP limit after explicit native source qualification.

The native rank readers, worn selection and extension readers are producers;
this phase preserves their exact ordered float32 addition and rate arithmetic.
"""
from els_server.domain.native_power_kernel import f32

PHASE_BEFORE=(25400, 21415, 21420, 28404, 28417, 28429, 27405, 22405, 30408, 22401, 25405, 25414, 27400, 2411, 2415, 27410, 30402, 29406, 29410, 31413, 23401, 23406, 23408, 30412, 22408, 32401, 32408, 32414, 29426, 22419, 21418, 24413, 33404, 33410, 33420)
UNIT_BEFORE=(24430, 24420, 31409, 31405, 31403, 26402, 26406, 26410)
PHASE_AFTER=(29422, 900406, 900414, 34401, 34411, 34419, 21431, 25427)
UNIT_AFTER=(22426, 24431, 27427, 30429, 23424, 33428, 29428, 28432, 26427, 32425, 34428, 35401, 35410, 35419, 35428)
PHASE_SKILLS=frozenset(PHASE_BEFORE+PHASE_AFTER)
UNIT_SKILLS=frozenset(UNIT_BEFORE+UNIT_AFTER)


def maximum(phase_values,unit_values,*,worn,flat,rate,extension5,extension17):
    if type(phase_values)is not dict or set(phase_values)!=PHASE_SKILLS:
        raise ValueError('All explicit native phase MP skill sources required')
    if type(unit_values)is not dict or set(unit_values)!=UNIT_SKILLS:
        raise ValueError('All explicit native unit MP skill sources required')
    phase={k:f32(v)for k,v in phase_values.items()}
    unit={k:f32(v)for k,v in unit_values.items()}
    total=f32(phase[PHASE_BEFORE[0]]+300.)
    for skill in PHASE_BEFORE[1:]:total=f32(total+phase[skill])
    for skill in UNIT_BEFORE:total=f32(total+unit[skill])
    total=f32(f32(worn)+total)
    for skill in PHASE_AFTER:total=f32(total+phase[skill])
    for skill in UNIT_AFTER:total=f32(total+unit[skill])
    coefficient=f32(f32(f32(extension5)*f32(.01))+f32(rate))
    total=f32(f32(coefficient*total)+total)
    return f32(f32(total+f32(flat))+f32(extension17))


def template_mp(record):
    import struct
    if type(record)is not bytes or len(record)!=232:
        raise ValueError('Current immutable native item record required')
    return f32(struct.unpack_from('<f',record,0x28)[0])


def equipment_mp(worn,excluded,added,*,selector,mode_side):
    """Whole1984460's separate MP collector; it is not the8A20E0 selector."""
    from els_server.domain.native_worn_item_inputs import slot_side
    if any(type(v)is not tuple or len(v)>2048 for v in(worn,excluded,added)):
        raise ValueError('Complete bounded ordered MP item vectors required')
    if type(selector)is not int or not 0<=selector<2**32 or type(mode_side)is not bool:
        raise ValueError('Explicit native MP selector and side context required')
    replaced={r['uid']for r in excluded if r is not None}
    selected=[]
    for row in worn:
        if row is None:raise ValueError('Native stored MP wrapper must own a business item')
        side=slot_side(row['slot_code'])
        if side!=2 and side!=int(selector!=0):continue
        if not row['template_present']or row['uid']in replaced:continue
        selected.append(row)
    for row in added:
        if row is None:continue
        if not row['template_present']:raise ValueError('Native added MP item requires its template')
        independent=not(row['flags4']&1)and row['flags8']&0xf8!=0x18
        if not independent and selector!=2:
            if row['flags4']&0xf000==0x1000:
                if int(mode_side)!=selector:continue
            elif selector==(0 if row['flags8']&4 else 1):continue
        selected.append(row)
    result=0.
    for row in selected:result=f32(result+f32(row['template_mp']))
    return result
