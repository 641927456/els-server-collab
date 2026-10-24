"""Owner-requested local ED packs; verified item records with local pricing.

Only the pack size and ED price are local policy. The item definition still has
to match the pinned client build and the reviewed 2026 reward catalogue.
"""
import functools
import hashlib
import json

from els_server.domain.activity_2026_stack_policy import effective_stack
from els_server.game_data import client_data
from els_server.paths import PROJECT_ROOT

CATALOG_SHA256 = '6160498a1c277d9b3d0819edbbce816991f4a7268acd7fc5069f1772060279a9'
TEMPLATE = 135948
NAME = '艾尔共鸣药水（100倍浓缩）'
CATEGORY = 41
PRICE = 1
QUANTITY = 1000
SKU = 1600135948
BULK_PACKS = {TEMPLATE: QUANTITY}


@functools.lru_cache(maxsize=1)
def definition():
    path = PROJECT_ROOT/'els_server/data/selected2026/rewards.json'
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CATALOG_SHA256:
        raise ValueError('Reviewed local reward catalogue changed')
    data = json.loads(raw)
    row = next((t for t in data['templates'] if t['template'] == TEMPLATE), None)
    if row is None or row['name'] != NAME:
        raise ValueError('Local shop pack item definition missing')
    item = client_data().item(TEMPLATE)
    if (item['name'] != NAME or item['item_type'] != 7
            or hashlib.sha256(item['record']).hexdigest() != row['record_sha256']):
        raise ValueError('Local shop pack item definition changed')
    return row


def register_inventory():
    from els_server.domain.inventory_items import (TEMPLATE_BAG_GROUPS,
                                                   TEMPLATE_MAX_STACKS,
                                                   VERIFIED_TEMPLATES)
    row = definition()
    expected = (row['metadata'], row['group'])
    if TEMPLATE in VERIFIED_TEMPLATES and (VERIFIED_TEMPLATES[TEMPLATE],
                                           TEMPLATE_BAG_GROUPS[TEMPLATE]) != expected:
        raise ValueError('Conflicting local shop pack classification')
    VERIFIED_TEMPLATES[TEMPLATE] = row['metadata']
    TEMPLATE_BAG_GROUPS[TEMPLATE] = row['group']
    TEMPLATE_MAX_STACKS[TEMPLATE] = effective_stack(row['max_stack'])


def offers():
    register_inventory()
    return (dict(sku=SKU, template=TEMPLATE, name=NAME, category=CATEGORY,
                 price=PRICE, quantity=QUANTITY),)
