"""Original option438 conditional-stat row and9859A0 append predicate."""
from els_server.domain.native_power_kernel import f32


def condition_input(definition):
    if type(definition)is not dict:raise ValueError('Original option definition required')
    kind=definition.get('m_eConditionStatChange',0)
    if kind is None:kind=0  # Original Lua nil removes the property.
    if type(kind)is not int or not 0<=kind<2**32:raise ValueError('Original condition type required')
    if kind==0:return (0,0.,0.,0.)
    return (kind,f32(0. if definition.get('m_fConditionValue')is None else definition['m_fConditionValue']),
        f32(0. if definition.get('m_fChangeStatValue')is None else definition['m_fChangeStatValue']),
        f32(0. if definition.get('m_fConditionLimitValue')is None else definition['m_fConditionLimitValue']))


def append_condition(existing, row, *, source_line, unit_line):
    if type(existing)is not tuple or len(existing)>1024:raise ValueError('Bounded original condition-vector required')
    if type(row)is not tuple or len(row)!=4 or type(row[0])is not int or not 0<=row[0]<2**32:raise ValueError('Original condition row required')
    normalized=(row[0],*map(f32,row[1:]))
    if any(type(v)is not int or not 0<=v<=65535 for v in(source_line,unit_line)):raise ValueError('Original uint16 class line required')
    if not row[0]or source_line and source_line!=unit_line:return existing
    if len(existing)==1024:raise ValueError('Original condition-vector bound')
    return existing+(normalized,)
