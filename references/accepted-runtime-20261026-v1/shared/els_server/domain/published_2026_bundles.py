"""Independent owned723635 catalogue from CN2026-07-29 published contents.

Import has no registration side effects. No recovered retail RewardID table is
required: the human approved published names/quantities mapped to fixed items.
"""
import functools,hashlib,json
from els_server.domain.activity_2026_stack_policy import effective_stack
from dataclasses import dataclass
from types import MappingProxyType
from els_server.game_data import client_data

DEFINITION_SHA256='53b00587f28204ed95d6e68a0ef2f6ed19e08b3da5b2a6ed947937ee0f3d8e00'

@dataclass(frozen=True)
class Output:
    template:int
    quantity:int
    metadata:int
    group:int
    max_stack:int

@dataclass(frozen=True)
class PublishedBundle:
    template:int
    metadata:int
    group:int
    max_stack:int
    outputs:tuple

_enabled=MappingProxyType({})

def enabled():return _enabled

def enable(raw):
    """Validate ALL source identities and inventory conflicts before mutation."""
    global _enabled
    if type(raw) is not bytes or hashlib.sha256(raw).hexdigest()!=DEFINITION_SHA256:
        raise ValueError('Pinned published2026 reward definition required')
    data=json.loads(raw);client=client_data()
    if client.manifest['catalog_sha256']!=data['catalog_sha256']:
        raise ValueError('Fixed item library changed')
    bundles={};policies={}
    for row in data['bundles']:
        for item in (row,*row['entries']):
            actual=client.item(item['template'])
            if (actual['name']!=item['name'] or actual['metadata']!=item['metadata']
                or hashlib.sha256(actual['record']).hexdigest()!=item['record_sha256']):
                raise ValueError('Published reward item identity changed')
            policy=(item['metadata'],item['group'],effective_stack(item['max_stack']))
            if item['template'] in policies and policies[item['template']]!=policy:
                raise ValueError('Conflicting published item policies')
            policies[item['template']]=policy
        outputs=tuple(Output(**{k:r[k] for k in Output.__dataclass_fields__}) for r in row['entries'])
        bundles[row['template']]=PublishedBundle(row['template'],row['metadata'],row['group'],row['max_stack'],outputs)
    if set(bundles)!={723612,723635}:raise ValueError('Selected bundle scope changed')
    if _enabled:
        if dict(_enabled)!=bundles:raise ValueError('Cannot replace active bundle contents')
        return _enabled
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES as meta,TEMPLATE_BAG_GROUPS as groups,TEMPLATE_MAX_STACKS as stacks
    for template,policy in policies.items():
        if template in meta and (meta[template],groups[template],stacks[template])!=policy:
            raise ValueError('Conflicting existing inventory policy')
    for template,(metadata,group,stack) in policies.items():
        meta[template]=metadata;groups[template]=group;stacks[template]=stack
    _enabled=MappingProxyType(bundles)
    from els_server.domain.cubes import catalog
    catalog.cache_clear()
    return _enabled

def entries():
    return tuple(MappingProxyType(dict(template=b.template,selection_count=0,
        entries=tuple(MappingProxyType(dict(template=r.template,quantity=r.quantity)) for r in b.outputs)))
        for b in _enabled.values())
