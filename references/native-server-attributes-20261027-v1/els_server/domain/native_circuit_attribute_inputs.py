"""Original6C9010 ordered active circuit option/weight producer."""
from els_server.domain.native_power_kernel import f32
from functools import lru_cache
from types import MappingProxyType


def weighted_options(active_slots,grid,definitions,ports):
    if (type(active_slots)is not tuple or len(set(active_slots))!=len(active_slots)
            or any(type(v)is not int or not 0<=v<16 for v in active_slots)
            or type(grid)is not tuple or len(grid)!=16
            or any(type(v)is not int or not 0<=v<2**31 for v in grid)):
        raise ValueError('Qualified original ordered active slots and complete grid required')
    weights={};steps={1:-4,2:1,3:4,4:-1}
    for position in active_slots:
        definition=definitions.get(grid[position])
        if definition is None:raise ValueError('Active original circuit option absent')
        value=definition.get('m_fCircuitMultipleRate')
        rate=f32(0. if value is None else value)
        if rate<=0.:continue
        shape=definition.get('m_eCircuitItemShapeType',0)
        for direction in ports.get(shape,()):
            if direction not in steps:raise ValueError('Original circuit direction required')
            target=position+steps[direction]
            weights[target]=f32(f32(rate-1.)+weights[target])if target in weights else rate
    return tuple((grid[position],weights.get(position,1.))for position in active_slots)


@lru_cache(maxsize=1)
def _source():
    from els_server.domain.equipment_circuit_rules import catalog
    source=catalog()
    return (MappingProxyType({int(key):value for key,value in source['options'].items()}),
        MappingProxyType({int(key):tuple(value)for key,value in source['ports'].items()}))


def collect(template,grid):
    """Reuse the installed finite circuit topology and canonical validation."""
    from els_server.domain.equipment_circuit_rules import active_slots
    slots=active_slots(template,grid);definitions,ports=_source()
    return weighted_options(tuple(slots),tuple(grid),definitions,ports)
