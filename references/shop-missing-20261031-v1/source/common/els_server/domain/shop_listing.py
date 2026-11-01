"""Owner-requested storefront selection, independent of inventory validity."""
import functools,hashlib,json
from els_server.paths import PROJECT_ROOT

# Ordinary recovery medicines were manually placed in the cash storefront.
# Keep their definitions and owned items; reject new cash-store purchases.
NPC_MEDICINES = frozenset((77000, 77010, 77170, 77180, 77190, 77270,
                          77420, 77430, 78902, 78925, 78927, 78930))


@functools.lru_cache(maxsize=1)
def ice_equipment():
    from els_server.game_data import CLIENT_SHA
    base=PROJECT_ROOT/'analysis/client-6c6b5180'
    data=json.loads((PROJECT_ROOT/'analysis/shop-standalone-20261015/ice-shop-exclusions.json').read_text(encoding='utf8'))
    if data['client_sha256']!=CLIENT_SHA:raise ValueError('Ice exclusion build mismatch')
    for source in data['sources']:
        if hashlib.sha256((base/source['path']).read_bytes()).hexdigest()!=source['sha256']:raise ValueError('Ice exclusion source changed')
    return frozenset(data['templates'])


@functools.lru_cache(maxsize=1)
def npc_items():
    from els_server.domain.shop_additions import catalog
    return frozenset(catalog('standalone')['npc_templates'])


def ordinary_cash_equipment(flags4):
    """Native ordinary cash profile, distinct from rare ice equipment."""
    return flags4 & 0xffff0000 == 0x00400000


def include_extended(offer):
    from els_server.domain.fashion_bundles import replaced_templates
    return (offer['template']!=274333  # Current profile already grants6; human requested removal.
            and offer['template'] not in NPC_MEDICINES
            and offer['template'] not in ice_equipment()
            and offer['template'] not in npc_items()
            and offer['template'] not in replaced_templates())
