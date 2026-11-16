"""Native Camilla shop source for the already registered starter Mod books."""
from functools import lru_cache
import json

from els_server.domain.promotion_reward_boxes import starter_rules

CAMILLA_NPC = 10017
CAMILLA_TOWNS = frozenset(range(20000, 20014))  # House 40016 includes Ruben via common scene 258.
SHOP_POLICY = 'native-camilla-starter-force-shop-v1'


@lru_cache(maxsize=1)
def starter_books():
    return frozenset(starter_rules())


def authorize_purchase(template, source):
    if source is None or template not in starter_books():
        return False
    from els_server.domain.raid_reward_items import validate_source
    from els_server.domain.npc_trade import stock
    source = validate_source(source)
    if source.kind != 'npc_trade':
        return False
    identity = json.loads(source._source)
    if identity.get('policy') != SHOP_POLICY:
        return False
    town, merchant = identity.get('town'), identity.get('merchant')
    if (identity.get('owner') != source.owner or identity.get('operation') != source.operation
            or merchant != CAMILLA_NPC or town not in CAMILLA_TOWNS
            or template not in stock().get((town, merchant), ())):
        raise ValueError('Camilla starter Force book requires its original shop')
    source.validate_template(template)
    return True
