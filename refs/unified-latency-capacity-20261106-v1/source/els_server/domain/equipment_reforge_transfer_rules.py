"""Finite normal transfer quotes; current atomic consumer has a separate scope.

The transaction validates current actor, both owned instances and costs. Its
versioned keep-each-life compatibility is nonretail; this module makes no writes.
"""
from dataclasses import dataclass
from pathlib import Path
import functools
import hashlib
import json

from els_server.domain import equipment_reforge_rules as reforge

DATA_SHA = 'a1a71a88a35300ed7c3ed11800bcc3c9a7d6179391f0954b7e17a60cafd0b878'
RUNTIME_ENABLED = True


@functools.lru_cache(maxsize=1)
def _policy():
    raw = (Path(__file__).resolve().parents[1] / 'data/equipment_reforge_transfer.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != DATA_SHA:
        raise ValueError('Transfer quotation policy identity')
    p = json.loads(raw)
    base = reforge.catalog()
    if (p['schema_version'] != 1 or p['policy_id'] != 'equipment-reforge-transfer-normal-life-compat-v1'
            or p['runtime_enabled'] is not True
            or p['parent_reforge_policy_sha256'] != reforge.DATA_SHA
            or p['client_sha256'] != base['client_sha256']
            or p['catalog_sha256'] != base['catalog_sha256']
            or p['source_resource_sha256'] != base['source_resource_sha256']):
        raise ValueError('Transfer quotation parent/client identity')
    if (p['material_flags_enabled'] != [0] or p['normal_actor_scope'] != 'both-current-actor-template-requirements-met-v1'
            or p['life_compatibility'] != dict(policy_id='reforge-transfer-keep-each-life-compat-v1', source_life='preserve_each_own', target_life='preserve_each_own', official=False)):
        raise ValueError('Transfer finite normal/life compatibility scope')
    approved=p['approved_templates']
    if (not isinstance(approved,list) or len(approved)!=368 or len(set(approved))!=368
            or 118251 in approved or any(type(t) is not int or str(t) not in base['targets'] for t in approved)):
        raise ValueError('Transfer independently reviewed finite normal templates')
    return p


@dataclass(frozen=True)
class TransferQuote:
    source_template: int
    target_template: int
    source_level: int
    target_old_level: int
    target_new_level: int
    target_family: int
    material_mode: str
    ed: int
    materials: tuple[tuple[int, int], ...]


def quote_pair(source_template, source_level, target_template, target_level, material_mode):
    """Check existing normal templates, adjacent families, same slot and levels.

    Modes are explicit resource names. No native flag0/1 interpretation is made.
    A quotation grants no permission to execute a transfer or alter any instance.
    """
    if (any(type(v) is not int for v in (source_template, source_level, target_template, target_level))
            or type(material_mode) is not str or material_mode not in ('normal', 'ticket')):
        raise ValueError('Transfer quotation input types/mode')
    p = _policy()
    if material_mode != 'normal' or source_template not in p['approved_templates'] or target_template not in p['approved_templates']:
        raise ValueError('Unadmitted transfer mode or finite normal template')
    source = reforge.require_target(source_template)
    target = reforge.require_target(target_template)
    if (source['reforge_class'] not in (1, 2, 3)
            or target['reforge_class'] != source['reforge_class'] + 1
            or source['part'] != target['part']):
        raise ValueError('Transfer adjacent family/same equipment slot')
    if not p['min_source_level'] <= source_level <= p['max_level']:
        raise ValueError('Transfer source level outside priced range')
    if not 0 <= target_level < p['min_source_level'] - p['level_reduction']:
        raise ValueError('Transfer recipient existing level too high')
    next_level = source_level - p['level_reduction']
    if next_level <= target_level:
        raise ValueError('Transfer must increase recipient level')
    price = p['profiles'][str(target['reforge_class'])][str(source_level)]
    demand = {int(k): v for k, v in price['essential'].items()}
    for template, count in price[material_mode].items():
        template = int(template)
        demand[template] = demand.get(template, 0) + count
    return TransferQuote(source_template, target_template, source_level, target_level,
                         next_level, target['reforge_class'], material_mode,
                         price['ed'], tuple(sorted(demand.items())))
