"""Original89C9D0 numerical phase, given explicit qualified type17 inputs.

This does not infer learned/equipped eligibility or evaluate the full original
skill numeric getter. Resource projections and supplied eligibility are separate.
No production registration, recursion, state persistence or power publication.
"""
import copy,math
from els_server.domain.native_power_kernel import f32

FIELDS={900407:0x36c,900410:0x3dc,900411:0x3b0}
PARAMETERS={900407:('SA_DROP_REL','SA_FIGHTING_POWER_ABS','SA_STAT_DROP_REL','SA_MAX_DROP_RATE_REL'),900410:('SA_DAMAGE_REL','SA_FIGHTING_POWER_ABS','SA_STAT_DAMAGE_REL','SA_MAX_DAMAGE_REL'),900411:('SA_DECREASE_COOLTIME_REL','SA_FIGHTING_POWER_ABS','SA_STAT_DECREASE_COOLTIME_REL','SA_MAX_COOLTIME_REL')}

def project_definition(skill,rank):
    sid=skill.get('m_eID')
    if sid not in FIELDS or skill.get('m_eType')!=17:raise ValueError('reviewed type17 definition required')
    if type(rank)is not int or not 1<=rank<=5:raise ValueError('reviewed source rank1..5 required')
    rows={v['m_wstrName']:v for k,v in skill.items()if k.startswith('NUMERICAL_DATA')}
    if set(rows)!=set(PARAMETERS[sid]):raise ValueError('complete exact four numerical names required')
    result={}
    for name,row in rows.items():
        if row.get('m_ParamType')!='f':raise ValueError('float source parameter required')
        for key in ('m_Value','m_Pvp_Rate'):
            values=row[key]
            if set(values)!={'0','1','2','3','4','5'} or values['0']is not None:raise ValueError('explicit source five-rank vector required')
        if f32(row['m_Pvp_Rate'][str(rank)])!=1.:raise ValueError('unverified source PvP multiplier')
        result[name]=f32(row['m_Value'][str(rank)])
    return result

def apply_qualified(current,inputs,power):
    if type(current)is not dict or not set(FIELDS.values())<=set(current):raise ValueError('explicit current three raw fields required')
    if type(inputs)is not dict or set(inputs)!=set(FIELDS):raise ValueError('explicit qualification and parameters for all three IDs required')
    power=f32(power)
    if power<0:raise ValueError('admitted nonnegative intermediate power required')
    result=copy.deepcopy(current);details=[]
    for sid,offset in FIELDS.items():
        row=inputs[sid]
        if type(row)is not dict or set(row)!={'eligible','parameters'}or type(row['eligible'])is not bool:raise ValueError('explicit supplied original qualification required')
        params=row['parameters']
        if type(params)is not dict or set(params)!=set(PARAMETERS[sid]):raise ValueError('complete explicit four parameters required')
        base,divisor,coefficient,cap=[f32(params[k])for k in PARAMETERS[sid]]
        if divisor<=0 or min(base,coefficient,cap)<0:raise ValueError('admitted positive divisor and nonnegative rates required')
        value=f32(current[offset])
        if not row['eligible']:
            details.append(dict(skill_id=sid,applied=False));continue
        steps=f32(math.floor(f32(power/divisor)))
        if sid==900407:
            first=f32(value+base*.01)
            scaled=f32(coefficient*f32(steps*f32(.01)))
            capped=min(f32(cap*f32(.01)),scaled)
            value=f32(first+capped)
        else:
            scaled=f32(coefficient*(steps*.01))
            capped=f32(cap*.01)if scaled>cap*.01 else scaled
            value=f32(f32(base*.01+capped)+value)
        result[offset]=value
        details.append(dict(skill_id=sid,applied=True,steps=steps,scaled=scaled,capped=capped,result=value))
    return dict(raw_fields=result,details=details,scope='offline_explicit_qualified_post_power_phase',actual_qualification_verified=False,power_publication=False)
