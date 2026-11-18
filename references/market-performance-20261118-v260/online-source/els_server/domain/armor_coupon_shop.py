"""Screenshot armour coupons, priced against the owner's420 coin/800M ED sale."""
from functools import lru_cache

COLORS=tuple(range(119309,119313))+tuple(range(168895,168899))
ROLES=tuple(range(119313,119317))+tuple(range(168905,168909))+tuple(range(168848,168852))
TEMPLATES=frozenset(COLORS+ROLES)


def price(coins):
    if type(coins) is not int or coins<0:raise ValueError('Integer coin price')
    return (coins*800_000_000+210)//420


@lru_cache(maxsize=1)
def offers():
    from els_server.game_data import client_data
    from els_server.domain.neblon_role_change_rules import definitions
    from els_server.domain.exascale_color_inventory import definitions as colors
    readers={row['template']:row for row in (*definitions(),*colors())}
    result=[]
    for template in COLORS+ROLES:
        row=readers[template]
        item=client_data().item(template)
        if (row['metadata'],row['group'],item['item_type'])!=(0,4,7):
            raise ValueError('Armor coupon native reader identity')
        result.append(dict(sku=1_200_000_000+template,template=template,name=item['name'],
                           category=32,quantity=1,price=price(1200 if template in COLORS else 1800)))
    return tuple(result)


def require_price_support(session,payload):
    from els_server.protocol.shop_messages import ed_purchase_request
    from els_server.storage.shop_state import _catalog
    from els_server.domain.season_pass_shop import offers as passes
    import time
    products=ed_purchase_request(payload)
    rows=_catalog(None).quantity_by_sku
    services={p['sku']:p for p in passes(int(time.time()))}
    for sku,count in products:
        row=rows.get(sku) or services.get(sku)
        if row and row['price']>=2**31 and getattr(session,'ed_price_version',1)!=2:
            raise ValueError('This ED price requires the current signed client support')
