"""Original A186C0 entry/merge metadata, with its actual source defaults."""
from els_server.domain.native_power_kernel import f32


def numeric(definition,key,default):
    value=definition.get(key)
    return default if value is None else value


def integer(value,low,high):
    if type(value)is not int or not low<=value<=high:raise ValueError('Qualified native metadata integer required')
    return value


def source_metadata(definition):
    if type(definition)is not dict:raise ValueError('Original option definition required')
    i32=lambda key,default:integer(numeric(definition,key,default),-2**31,2**31-1)
    flag=lambda key:int(i32(key,0)!=0)
    return dict(kind=i32('TYPE',0),
        source_line=integer(numeric(definition,'m_usUnitClassLineType',0),0,65535),
        condition_enabled=flag('m_bIsEnableEnchantLevel'),
        condition_kind=i32('m_eEnableEnchantLevelTarget',0),
        condition_scale=f32(numeric(definition,'m_fEnchantLevelRate',.01)),
        pvp_rate=f32(numeric(definition,'m_fPVPRate',1.)),
        native_1f0=i32('DUNGEON_ONLY_TYPE',0),
        native_1f4=flag('DUNGEON_ONLY'),native_1f5=flag('PVP_ONLY'),
        native_1f6=flag('m_bOnlyDevildom'),native_640=i32('m_iBelowErLevel',2**31-1))


def ordinary_entry(metadata,*,resonance_level,mode):
    #88A289..88A2D1; other entry families keep separate original predicates.
    integer(resonance_level,-2**31,2**31-1);integer(mode,0,1)
    if type(metadata)is not dict or not {'native_1f0','native_1f4','native_1f5','native_1f6','native_640'}<=set(metadata):
        raise ValueError('Complete original ordinary entry metadata required')
    if metadata['native_1f0']!=0 or metadata['native_1f6']==1:return False
    if metadata['native_1f4'if mode else'native_1f5']!=0:return False
    return metadata['native_640']>=resonance_level
