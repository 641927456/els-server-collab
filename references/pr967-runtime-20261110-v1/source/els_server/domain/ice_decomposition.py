"""Owner's 2026-11-05 rule: each ice costume returns 45 unidentified El Shards."""
import functools
import hashlib

from els_server.game_data import client_data

POLICY = 'ice-costume-fixed-45-20261105'
REWARD = 130047
QUANTITY = 45


@functools.lru_cache(maxsize=1)
def templates():
    from els_server.domain.inventory_items import role_ice_catalog
    return frozenset(row['template'] for row in role_ice_catalog()['rewards']
                     if row['group'] == 27)


def quote(item):
    if item['template'] not in templates():
        return None
    from els_server.domain.boosting_2026_item_policy import item_deadline
    if (item['group'] != 27 or item['count'] != 1 or item.get('sealed')
            or item_deadline(item) is not None):
        raise ValueError('Permanent unsealed bag ice costume required')
    row = client_data().item(item['template'])
    # Original 22937B0 admits cash equipment through its cash-price membership;
    # the pinned ice catalog contains its costume outputs, not machines or cubes.
    if not row['flags4'] & 1 or row['flags4'] & 32 or row['item_type'] not in (1, 2, 3):
        raise ValueError('Ice costume native decomposition eligibility')
    return dict(template=REWARD, quantity=QUANTITY, input_template=item['template'],
                policy_id=POLICY, record_sha256=hashlib.sha256(row['record']).hexdigest())


def reward_definition():
    from els_server.domain.inventory_items import (
        VERIFIED_TEMPLATES, TEMPLATE_BAG_GROUPS, TEMPLATE_MAX_STACKS)
    row = client_data().item(REWARD)
    if ((row['item_type'], row['metadata']) != (7, 2)
            or hashlib.sha256(row['record']).hexdigest()
            != 'bc6d9a1e7bce68f702ec66b08b3c54036f1b85aaa7c498f22bd4ee6b1867c514'):
        raise ValueError('Unidentified El Shard original definition')
    if (VERIFIED_TEMPLATES.get(REWARD), TEMPLATE_BAG_GROUPS.get(REWARD),
            TEMPLATE_MAX_STACKS.get(REWARD)) != (2, 4, 999):
        raise ValueError('Unidentified El Shard admitted inventory definition')
    return dict(template=REWARD, metadata=2, group=4, max_stack=999)
