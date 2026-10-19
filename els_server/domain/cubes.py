"""Shared inventory-cube view; fixed and selected rewards use the same ledger."""
import functools
from types import MappingProxyType
from els_server.domain.fixed_cubes import catalog as fixed
from els_server.domain.select_cubes import catalog as selected


@functools.lru_cache(maxsize=1)
def catalog():
    result={t:MappingProxyType(dict(row,selection_count=0,
        entries=[dict(template=row['reward'],quantity=row['quantity'],name=row['reward_name'])])) for t,row in fixed().items()}
    for t,row in selected().items():
        if t in result:raise ValueError('Duplicate inventory cube mode')
        result[t]=row
    from els_server.domain.regional_boss_cubes import catalog as regional
    for t,row in regional().items():
        if t in result:raise ValueError('Duplicate regional cube')
        result[t]=MappingProxyType(row)
    return MappingProxyType(result)
