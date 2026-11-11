"""The three retail activation products for the current Magmelia Express."""
from datetime import datetime
from functools import lru_cache
from hashlib import sha256

from els_server.domain.periodic_activities import CN, active_season, catalog
from els_server.game_data import client_data


PRICE = 50
SEASON = 12
SKU_BASE = 1200000000
PRODUCTS = {
    723659: (2, 'd88a21779f4c37711c392dca0e93bc1765d25d8231a48aa1c25d49c732f6fb2d'),
    723661: (3, 'a7e33a5c68606eb6d670fef654599ff38d38fc36543f8518ffa3912aac48d060'),
    723748: (4, '925ff57e816337df14978ffd28408227b3ad08f7f716c529b3f669274e8b90a1'),
}
SKUS = {SKU_BASE + template: category for template, (category, _) in PRODUCTS.items()}


def _cn_time(value):
    return int(datetime.fromisoformat(value).replace(tzinfo=CN).timestamp())


EARLY_END = _cn_time('2026-11-18 09:59:00')
HAIVAN_START = _cn_time('2026-08-26 09:00:00')


def active_templates(now):
    season = active_season(now)
    if season is None or season[2] != SEASON:
        return ()
    return tuple(template for template, (category, _) in PRODUCTS.items()
                 if (now >= HAIVAN_START if category == 4 else now < EARLY_END))


def on_sale(category, now):
    return any(PRODUCTS[template][0] == category for template in active_templates(now))


@lru_cache(maxsize=3)
def _offer(template):
    category, digest = PRODUCTS[template]
    config = catalog()['passes'][str(category)]
    item = client_data().item(template)
    if (config['SeasonPassNo'] != SEASON
            or (template, 2) not in {(r['1'], r['2']) for r in config['SeasonPassCashItem'].values()}
            or sha256(item['record']).hexdigest() != digest):
        raise ValueError('Magmelia Express shop product identity')
    return dict(sku=SKU_BASE + template, template=template, name=item['name'],
                category=32, price=PRICE, quantity=1)


def offers(now):
    return tuple(_offer(template).copy() for template in active_templates(now))


def prepared_offer_sets():
    """Each nonempty sale set at the start of a catalogue phase."""
    return {templates: tuple(_offer(template).copy() for template in templates)
            for now in (HAIVAN_START - 1, HAIVAN_START, EARLY_END)
            if (templates := active_templates(now))}
