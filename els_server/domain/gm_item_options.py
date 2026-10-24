"""GM item option presets. Values are validated by the native-consumer rules."""
import functools

LABELS = {
    'm_fIncreaseDmgRateToBoss': 'BOSS伤害',
    'm_fIncreaseDefRateToBoss': 'BOSS防御',
    'm_fAllSkillDamageIncreaseRate': '全技能伤害',
    'm_fCritical': '暴击伤害',
    'm_fDamageMaximizeRate': '极大化',
    'm_fAttackReactValue': '攻击反应',
    'm_IncreaseHP': 'HP',
    'm_fAdditionalDefenceValue': '额外防御',
    'm_fAdditionalAttackedDamageValue': '被击伤害',
    'm_fMasterSkillIncreaseDamage': '超技能伤害',
    'm_fDecreaseMasterSkillCooltimeGrade_All': '超技能冷却',
    'm_fDecrease_MPCostRate': 'MP消耗',
    'm_fMoveSpeed': '移动速度',
    'm_fJumpSpeed': '跳跃速度',
    'm_iAnimationSpeedRate': '动作速度',
    'm_fHPRecoveryRate': 'HP恢复',
    'm_fReduceRecoveryItemCooltime': '恢复道具冷却',
    'm_fSkillAdditionalPowerRate': '技能额外威力',
    'm_fAccumulationSocketValue': '累积镶嵌值',
    'm_fNormalSkillCoolTimeResetRate_OperatorType_Add': '技能冷却初始化概率',
    'm_fProbability': '触发概率',
    'm_fIntervalTime': '间隔时间',
    'm_fTickInterval': '触发间隔',
    'm_fTotalDivideTime': '持续时长',
    'm_fHyperModeTime': '超载时长',
    'm_sBuffLevel': 'Buff等级',
    'BUFF_FACTOR_ID': 'Buff编号',
    'm_PowerRate': '威力倍率',
    'm_SkillType': '技能类型',
    'm_eSkillIDForAdditionalPowerRate': '技能编号',
    'm_fEffectiveValue': '效果值',
    'm_fCircuitMultipleRate': '电路倍率',
    'm_iAddMpValue': 'MP恢复',
    'm_fIncreaseDmgEnemyHPFew_DmgRate': '低HP敌人增伤',
    'm_iIncreaseDmgEnemyHPFew_HPPercent': '低HP阈值',
    'm_fAddAttackedCommandDamageValue': '指令攻击伤害',
    'm_fPercentCritical': '暴击率',
    'm_IncreaseDefPhysic': '物理防御',
    'm_IncreaseDefMagic': '魔法防御',
    'm_iImpactedSocketID': '镶嵌编号',
    'm_eTypeSetItemEffectEx': '效果类型',
    'm_SkillLevelUpID': '技能等级提升',
    'm_SetMonsterIDDamageReduced': '特定怪物减伤',
    'm_setMonsterIDForDamageUp': '特定怪物增伤',
    'm_setMonsterIDForEvade': '特定怪物闪避',
    'RESIST_ENCHANT': '属性抗性',
    'm_fPVPRate': 'PVP修正',
    'm_fPartyBuffAdditionalDefenceValueForCapability': '组队防御',
    'm_fPartyBuffIncreaseAtkPhysicForCapability': '组队物攻',
    'm_fPartyBuffIncreaseAtkMagicForCapability': '组队魔攻',
    'm_fPartyBuffAllSkillDamageIncreaseForCapability': '组队全技能伤害',
    'm_fPartyBuffCriticalForCapability': '组队暴击',
    'm_fPartyBuffAnimationSpeedRateForCapability': '组队动作速度',
    'm_fPartyBuffMoveSpeedRateForCapability': '组队移动速度',
}
COLORS = {1: '蓝', 2: '红', 3: '黄'}
SECONDS = {'m_fIntervalTime', 'm_fTickInterval', 'm_fTotalDivideTime', 'm_fHyperModeTime'}


def _stat_text(key, value):
    label = LABELS.get(key)
    if label is None:
        if not key.startswith('m_'):
            return None
        label = key.split('_', 2)[-1]
    if key in SECONDS:
        return f'{label} {value:g}s'
    if key.startswith(('m_f', 'm_Increase', 'm_PowerRate', 'm_fPVPRate')):
        return f'{label} {value*100:g}%'
    return f'{label} {value:g}'


def _circuit_label(row):
    parts = [f"颜色{COLORS.get(row.get('m_eCircuitItemColorType'), row.get('m_eCircuitItemColorType'))}",
             f"形状{row.get('m_eCircuitItemShapeType')}"]
    rate = row.get('m_fCircuitMultipleRate')
    if isinstance(rate, (int, float)) and rate:
        return ' · '.join(parts + [f'链接电路属性合计 ×{rate:g}（T型专属）'])
    stats = []
    for key, value in row.items():
        if key not in LABELS or key.startswith('BUFF_') or not isinstance(value, (int, float)) or not value:
            continue
        if key in ('m_eTypeSetItemEffectEx', 'm_iImpactedSocketID', 'm_eSkillIDForAdditionalPowerRate'):
            continue
        text = _stat_text(key, value)
        if text:
            stats.append(text)
    special = []
    for key in ('m_SkillLevelUpID', 'm_SetMonsterIDDamageReduced',
                'm_setMonsterIDForDamageUp', 'm_setMonsterIDForEvade'):
        value = row.get(key)
        if isinstance(value, str) and value and value.strip().casefold() not in ('group 0', 'group0'):
            special.append(f'{LABELS[key]}（{value}）')
    resist = row.get('RESIST_ENCHANT')
    if isinstance(resist, dict):
        names = {'BLAZE': '火', 'WATER': '水', 'WIND': '风', 'LIGHT': '光',
                 'DARK': '暗', 'NATURE': '自然'}
        values = [f'{names.get(key, key)}{value}' for key, value in resist.items() if value]
        if values:
            special.append('属性抗性 '+'/'.join(values))
    tail = stats[:4]+special[:2]
    if not tail:
        tail = ['特殊效果（组）']
    return ' · '.join(parts + tail)


@functools.lru_cache(maxsize=256)
def spec(template):
    from els_server.domain import equipment_circuit_rules as circuits
    row = circuits.material(template)
    if row is not None:
        catalog = circuits.catalog()['options']
        choices = []
        seen = set()
        for option in row['options']:
            data = catalog.get(str(option))
            if data is None:
                continue
            label = _circuit_label(data)
            if label in seen:
                continue
            seen.add(label)
            choices.append(dict(id=option, label=label))
        choices.sort(key=lambda choice: (0 if '链接电路属性合计' in choice['label'] else 1, choice['label']))
        return dict(kind='choice', group='1', choices=choices)
    if circuits.target(template) is not None:
        return dict(kind='grid', group='28', slots=16, choices=[])
    return dict(kind='json', choices=[])


def apply(template, groups):
    """Validate a GM-chosen option set with the same consumers the game uses."""
    if groups in (None, {}):
        return None
    if not isinstance(groups, dict) or not groups:
        raise ValueError('属性预设格式无效')
    from els_server.domain import equipment_circuit_rules as circuits
    if circuits.material(template) is not None:
        if set(groups) != {'1'}:
            raise ValueError('电路材料只能选择一条属性')
        return {'1': circuits.validate_material(template, groups['1'])}
    if circuits.target(template) is not None:
        if set(groups) != {'28'}:
            raise ValueError('防具电路需要 16 格属性网格')
        return {'28': circuits.validate_grid(template, groups['28'])}
    from els_server.domain.sage_sockets import validate
    return validate(template, groups)
