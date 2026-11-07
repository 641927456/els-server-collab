"""Original type30 predicates; other condition families remain unimplemented."""
from els_server.domain.titles import catalog,eligible

def rules():
    data=catalog();result=[]
    identities=(1690,1700,1710,1720,1730);levels=(1,20,40,60,80)
    if sorted(int(k) for k,m in data['missions'].items() if m['m_eClearType']==30)!=list(identities):raise ValueError('Level title source coverage changed')
    for identity,level in zip(identities,levels):
        m=data['missions'][str(identity)];s=data['submissions'][str(identity)];t=data['titles'][str(identity)]
        if (m['m_iTitleID']!=identity or m['m_iConditionLv']!=1 or any(m[k] for k in ('m_sPeriod','m_bAccountMission','m_eConditionUnitType','m_eConditionUnitClass'))
            or any(m['m_iConditionClearMissionID'].values()) or [v for v in m['m_SubMission'].values() if v]!=[identity]
            or s['m_eClearType']!=30 or s['m_ClearCondition']!={'m_iAchieveLevel':level}
            or t['m_bAccountTitle'] or t['m_iOpenLevel']!=1 or t['m_eUnitType'] or t['m_eUnitClass'] or t.get('m_eTitleCanUseType',0)):
            raise ValueError('Unsupported level title condition change')
        result.append((identity,level))
    return tuple(result)

def achieved(character):
    level=character['level']
    if type(level) is not int or not 1<=level<=99:raise ValueError('Committed character level')
    return tuple(identity for identity,target in rules() if level>=target and eligible(character,identity))
