"""Original option source probability and capability-map leaves."""
from els_server.domain.native_power_kernel import f32


def i32(value):
    if type(value) is not int or not -2**31<=value<2**31:
        raise ValueError('Original int32 source field required')
    return value


def source_map_inputs(definition):
    if type(definition) is not dict:raise ValueError('Original option definition required')
    kind=i32(definition.get('m_eMultiplyStatType',-1))
    basic=f32(definition.get('m_fBasicMultiplyStatValueForCapability',0.))
    enchant=f32(definition.get('m_fEnchantMultiplyStatValueForCapability',0.))
    rate=f32(definition.get('m_fIncreaseDmgEnemyHPFew_DmgRate',0.))
    percent=i32(definition.get('m_iIncreaseDmgEnemyHPFew_HPPercent',0))
    flag=definition.get('m_bIncreaseDmgEnemyHPFew_IsDown',0)
    if type(flag) is not int or flag not in(0,1):raise ValueError('Qualified original probability flag required')
    probability={} if rate==0. else {(percent if percent else 30,flag):rate}
    additional=(i32(definition.get('m_iIncreaseDmgEnemyHPFew_HPPercent_OperatorType_Add',0)),
        f32(definition.get('m_fIncreaseDmgEnemyHPFew_DmgRate_OperatorType_Add',0.)))
    return dict(capability=(kind,basic,enchant),probability=probability,additional=additional)


def merge_map_inputs(destination_capability, destination_probability, destination_additional, source, *,
                     condition_enabled, condition_value, pvp, pvp_rate, weight,
                     source_line, unit_line):
    if type(source) is not dict or set(source)!={'capability','probability','additional'}:
        raise ValueError('Complete original option map inputs required')
    if type(destination_capability) is not dict or type(destination_probability) is not dict:
        raise ValueError('Explicit original destination maps required')
    if len(destination_capability)>1024 or len(destination_probability)>1024:raise ValueError('Bounded original map required')
    capability={i32(k):f32(v)for k,v in destination_capability.items()}
    def pair(key):
        if type(key) is not tuple or len(key)!=2 or type(key[1]) is not int or key[1]not in(0,1):raise ValueError('Original probability pair key required')
        return i32(key[0]),key[1]
    probability={pair(k):f32(v)for k,v in destination_probability.items()}
    if type(condition_enabled) is not int or not 0<=condition_enabled<=255:raise ValueError('Original byte condition flag required')
    value=f32(i32(condition_value))
    if type(pvp) is not bool:raise ValueError('Explicit native phase flag required')
    if any(type(v)is not int or not 0<=v<=65535 for v in(source_line,unit_line)):raise ValueError('Original uint16 class line required')
    factor=f32((f32(pvp_rate)if pvp else 1.)*f32(weight))
    if type(source['capability'])is not tuple or len(source['capability'])!=3:raise ValueError('Original capability source triple required')
    if type(source['probability'])is not dict or len(source['probability'])>1024:raise ValueError('Bounded original probability source map required')
    kind,basic,enchant=source['capability'];kind=i32(kind);basic=f32(basic);enchant=f32(enchant)
    additional=source['additional']
    if type(additional)is not tuple or len(additional)!=2:raise ValueError('Original additional-damage pair required')
    i32(additional[0]);f32(additional[1])
    if type(destination_additional)is not tuple or len(destination_additional)!=2:raise ValueError('Original destination additional-damage pair required')
    current=(i32(destination_additional[0]),f32(destination_additional[1]))
    if source_line and source_line!=unit_line:return capability,probability,current
    if kind!=-1:
        capability[kind]=f32(basic+capability.get(kind,0.))
        if condition_enabled==1:capability[kind]=f32(f32(value*enchant)+capability[kind])
    for key,row in sorted(source['probability'].items()):
        key=pair(key);contribution=f32(factor*f32(row))
        probability[key]=f32(contribution+probability.get(key,0.))
    combined=((current[0]+additional[0]+2**31)%2**32-2**31,f32(f32(additional[1])+current[1]))
    return capability,probability,combined
