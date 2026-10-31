"""Current option properties consumed by the second category-map phase."""
from els_server.domain.native_power_kernel import f32

CAPABILITY_PROPERTIES={
    'm_fPartyBuffIncreaseAtkPhysicForCapability':0x598,
    'm_fPartyBuffIncreaseAtkMagicForCapability':0x59c,
    'm_fPartyBuffIncreaseDefPhysicForCapability':0x5a0,
    'm_fPartyBuffIncreaseDefMagicForCapability':0x5a4,
    'm_fPartyBuffCriticalForCapability':0x5a8,
    'm_fPartyBuffDamageMaximizeRateForCapability':0x5ac,
    'm_fPartyBuffPercentCriticalForCapability':0x5b0,
    'm_fPartyBuffAllSkillDamageIncreaseForCapability':0x5b4,
    'm_fPartyBuffAdditionalAttackValueForCapability':0x5b8,
    'm_fPartyBuffAnimationSpeedRateForCapability':0x5bc,
    'm_fPartyBuffMoveSpeedRateForCapability':0x5c0,
    'm_fPartyBuffAdditionalDefenceValueForCapability':0x5c4,
}
RESISTANCE_KEYS=('BLAZE','WATER','NATURE','WIND','LIGHT','DARK')
CATEGORIES={1:6,2:8,3:14,4:15,5:16,6:13,7:22,8:23,9:24,10:25}


def category_vector(raw):
    if raw is None:return ()
    if type(raw)is not dict:raise ValueError('Original ordered Lua category table required')
    if '0'in raw and raw['0']is not None:raise ValueError('Qualified Lua sequence origin required')
    count=len(raw)-int('0'in raw)
    if count>16384 or set(raw)-{'0'}!={str(i)for i in range(1,count+1)}:
        raise ValueError('Complete dense Lua category sequence required')
    result=[]
    for i in range(1,count+1):
        value=raw[str(i)]
        if type(value)is not int or value not in CATEGORIES:
            raise ValueError('Unqualified current native skill category')
        result.append(CATEGORIES[value])
    return tuple(result)


def extended_source_inputs(definition):
    if type(definition)is not dict:raise ValueError('Original current option dictionary required')
    group=definition.get('m_eSkillIDForAdditionalPowerRate','Group 0')
    if type(group)is not str or not group.startswith('Group ') or not group[6:].isdigit():
        raise ValueError('Qualified current source group name required')
    # The native branch compares the actual string before parsing its suffix.
    active=group!='Group 0'
    raw=definition.get('RESIST_ENCHANT',{})
    if type(raw)is not dict:raise ValueError('Original resistance property dictionary required')
    resist=[]
    for key in RESISTANCE_KEYS:
        value=raw.get(key,0)
        if type(value)is not int or not -2**31<=value<2**31:
            raise ValueError('Original signed resistance source required')
        resist.append(value)
    # The seventh native word remains zero in the current option property
    # loader. An arbitrary ALL property is not an additional resistance.
    return dict(skills=category_vector(definition.get('m_SkillType'))if active else (),
        skill_rate=f32(definition.get('m_fSkillAdditionalPowerRate',0.))if active else 0.,
        alternate_skills=category_vector(definition.get('m_vecSkillTypeForCapability')),
        alternate_rate=f32(definition.get('m_fAdditionalPowerForCapability',0.)),
        source_resistances=(*resist,0),
        capability_fields={offset:f32(definition.get(key,0.))for key,offset in CAPABILITY_PROPERTIES.items()})
