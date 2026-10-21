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
    from els_server.domain.ep_essence_bag import entry as essence_pouch
    pouch=essence_pouch()
    if pouch['template'] in result:raise ValueError('Duplicate Essence pouch')
    result[pouch['template']]=MappingProxyType(pouch)
    from els_server.domain.growing_adventure_kit import BOX,entry
    if BOX in result:raise ValueError('Duplicate growing adventure kit')
    result[BOX]=MappingProxyType(entry())
    from els_server.domain.regional_boss_cubes import catalog as regional
    for t,row in regional().items():
        if t in result:raise ValueError('Duplicate regional cube')
        result[t]=MappingProxyType(row)
    from els_server.domain.published_2026_bundles import entries
    for bundle in entries():
        if bundle['template'] in result:raise ValueError('Duplicate selected consumable bundle')
        result[bundle['template']]=bundle
    from els_server.domain.boosting_2026_force_rewards import entries as force_entries
    for box in force_entries():
        if box['template'] in result:raise ValueError('Duplicate selected force box')
        result[box['template']]=box
    from els_server.domain.boosting_2026_participation_gear import entry as gear_entry
    from els_server.domain.boosting_2026_fashion_rewards import entries as fashion_entries
    gear=gear_entry()
    for box in ((gear,) if gear is not None else ()) + tuple(fashion_entries()):
        if box['template'] in result:raise ValueError('Duplicate original growth gear box')
        result[box['template']]=box
    from els_server.domain.boosting_2026_nested_capacity import entry as capacity_entry
    capacity=capacity_entry()
    if capacity is not None:
        if capacity['template'] in result:raise ValueError('Duplicate nested capacity box')
        result[capacity['template']]=capacity
    from els_server.domain.boosting_2026_title_rewards import entry as title_entry
    title=title_entry()
    if title is not None:
        if title['template'] in result:raise ValueError('Duplicate selected title support box')
        result[title['template']]=title
    from els_server.domain.boosting_2026_accessories import entries as accessory_entries
    for box in accessory_entries():
        if box['template'] in result:raise ValueError('Duplicate selected accessory box')
        result[box['template']]=box
    return MappingProxyType(result)
