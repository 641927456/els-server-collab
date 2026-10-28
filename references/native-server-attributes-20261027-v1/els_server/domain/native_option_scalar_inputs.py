"""Original option catalog scalar normalization, before activation and merge.

The source is a catalog definition, never a player-reported attribute record.
These57 leaves are distinct from final seven stats and conditional maps.
"""
from els_server.domain.native_power_kernel import f32

# A186C0 property body; native float conversion precedes each multiplier.
LAYOUT = {
    'm_fHyperModeTime': (0x20, 1.5),
    'm_fMoveSpeed': (0x10, 100.0),
    'm_fJumpSpeed': (0x14, 100.0),
    'm_fHyperModeChargeRate': (0x1c, 100.0),
    'm_fAdditionalAttackValue': (0x114, 100.0),
    'm_fAdditionalDefenceValue': (0x110, 100.0),
    'm_fAdditionalAttackedDamageValue': (0x118, 1.0),
    'm_fAddAttackedCommandDamageValue': (0x11c, 1.0),
    'm_iAnimationSpeedRate': (0x18, 1.0),
    'm_fPercentCritical': (0xf4, 100.0),
    'm_fCritical': (0xf8, 1.0),
    'm_IncreaseHP': (0x6b8, 100.0),
    'm_IncreaseAtkPhysic': (0x6c0, 1.0),
    'm_IncreaseAtkMagic': (0x6c4, 1.0),
    'm_IncreaseDefPhysic': (0x6c8, 1.0),
    'm_IncreaseDefMagic': (0x6cc, 1.0),
    'm_fAttackReactValue': (0x448, 1.0),
    'm_fIncreaseAtkPhysicForCapability': (0x560, 1.0),
    'm_fIncreaseAtkMagicForCapability': (0x564, 1.0),
    'm_fIncreaseDefPhysicForCapability': (0x568, 1.0),
    'm_fIncreaseDefMagicForCapability': (0x56c, 1.0),
    'm_fAnimationSpeedRateForCapability': (0x570, 1.0),
    'm_fAdditionalAttackValueForCapability': (0x574, 1.0),
    'm_fDamageMaximizeRateForCapability': (0x578, 1.0),
    'm_fPercentCriticalForCapability': (0x57c, 1.0),
    'm_fCriticalForCapability': (0x580, 1.0),
    'm_fAllSkillDamageIncreaseRateForCapability': (0x584, 1.0),
    'm_fAllSkillCooltimeIncreaseRateForCapability': (0x588, 1.0),
    'm_fAdditionalAttackedDamageValueForCapability': (0x58c, 1.0),
    'm_fAdditionalDefenceValueForCapability': (0x590, 1.0),
    'm_fAddAttackedCommandDamageValueForCapability': (0x594, 1.0),
    'm_fAdaptabilityForCapability': (0x5e8, 1.0),
    'm_fHyperAdaptabilityForCapability': (0x5ec, 1.0),
    'm_fDamageMaximizeRate': (0x198, 100.0),
    'm_fNormalSkillCoolTimeResetRate': (0x558, 1.0),
    'm_fAtkPhysicPiercingRate': (0x360, 1.0),
    'm_fAtkMagicPiercingRate': (0x364, 1.0),
    'm_fHPRecoveryRate': (0x368, 1.0),
    'm_fIncreaseDmgRateToBoss': (0x370, 1.0),
    'm_fIncreaseDefRateToBoss': (0x374, 1.0),
    'm_fDecrease_MPCostRate': (0x410, 1.0),
    'm_fAllSkillDamageIncreaseRate': (0x41c, 1.0),
    'm_fAdaptability': (0x4f0, 1.0),
    'm_fHyperAdaptability': (0x4f4, 1.0),
    'm_fNormalSkillCoolTimeResetRate_OperatorType_Add': (0x61c, 1.0),
    'm_fMPIncByAttack_ReturnRate': (0x180, 100.0),
    'm_fMPIncByAttacked_ReturnRate': (0x188, 100.0),
    'm_IncreaseMP': (0x6bc, 1.0),
    'm_fDecreaseActiveSkillCooltime': (0x390, 1.0),
    'm_fDecrease1stSA_SkillCooltime': (0x394, 1.0),
    'm_fDecrease2ndSA_SkillCooltime': (0x398, 1.0),
    'm_fDecrease3rdSA_SkillCooltime': (0x39c, 1.0),
    'm_fAllSkillCooltimeDecreaseRate': (0x418, 1.0),
    'm_fActiveSkillAdditionalPowerRate': (0x3e8, 1.0),
    'm_f1stSASkillAdditionalPowerRate': (0x3ec, 1.0),
    'm_f2ndSASkillAdditionalPowerRate': (0x3f0, 1.0),
    'm_f3rdSASkillAdditionalPowerRate': (0x3f4, 1.0),
}
FIELDS = frozenset(offset for offset, scale in LAYOUT.values())


def scalar_inputs(definition):
    """Normalize every scalar leaf; caller retains all other definition groups."""
    if type(definition) is not dict:
        raise ValueError('Original option catalog dictionary required')
    output = {}
    for key, (offset, scale) in LAYOUT.items():
        value = f32(definition[key]) if key in definition else 0.
        if offset in (0x180, 0x188):
            shared = f32(definition["m_fMPMultiplyByAll"]) if "m_fMPMultiplyByAll" in definition else 0.
            value = f32(shared + value)
        output[offset] = f32(value * scale)
    return output
