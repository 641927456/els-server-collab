"""A186C0's348 capability rows from the original set-effect source fields.

B23F70 reads the referenced buff factor ID and accumulation float at row+2C.
Merely attaching BUFF_FACTOR_ID does not append a row. The separate ordinary
buff consumer still owns the other source properties and effect lifecycle.
"""
from els_server.domain.native_power_kernel import f32

EPSILON=1.1920928955078125e-7  # Original2E6550 constant43707E4.
KEYS=('BUFF_FACTOR_ID','m_sBuffLevel','m_eTypeSetItemEffectEx',
      'm_bKillAbsoluteMonster','m_fIncreaseDmgEnemyHPFew_HpRate',
      'm_fActiveCheckMp','m_iActiveNumOfDebuff',
      'm_bInsertBuffWhenResetSkillCoolTime','m_fAccumulationSocketValue')


def integer(definition,key,low,high):
    value=definition.get(key)
    if value is None:value=0
    if type(value)is not int or not low<=value<=high:
        raise ValueError('Qualified native set-effect integer required')
    return value


def capability_rows(definition):
    if type(definition)is not dict:raise ValueError('Original option definition required')
    factor=integer(definition,'BUFF_FACTOR_ID',0,2**32-1)
    level=integer(definition,'m_sBuffLevel',-32768,32767)
    kind=integer(definition,'m_eTypeSetItemEffectEx',-2**31,2**31-1)
    kill=integer(definition,'m_bKillAbsoluteMonster',-2**31,2**31-1)!=0
    hp=integer(definition,'m_fIncreaseDmgEnemyHPFew_HpRate',-2**31,2**31-1)
    mp=f32(0. if definition.get('m_fActiveCheckMp')is None else definition['m_fActiveCheckMp'])
    debuffs=integer(definition,'m_iActiveNumOfDebuff',-2**31,2**31-1)
    reset=integer(definition,'m_bInsertBuffWhenResetSkillCoolTime',-2**31,2**31-1)!=0
    accumulation=f32(0. if definition.get('m_fAccumulationSocketValue')is None else definition['m_fAccumulationSocketValue'])
    active=kill or hp>=1 or kind in(15,51)or abs(mp)>EPSILON or debuffs>0 or reset
    # ACE382..ACE437 diagnoses a missing factor/zero level and skips append.
    # Preserve that no-contribution result; never invent a default buff level.
    return ((factor,accumulation),)if active and factor and level else ()
