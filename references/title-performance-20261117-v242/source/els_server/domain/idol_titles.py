"""Owner-approved permanent collaboration titles and their ED shop offers."""
from els_server.game_data import client_data

PRICE_ED = 100_000_000
# Existing consumables; use the ordinary title item ownership/receipt path.
ITEM_TITLES = {
    286910: 38070,
    287337: 38080,
    287338: 38090,
    287339: 38100,
    287340: 38110,
    287341: 38120,
    287342: 38130,
}
TITLE_IDS = tuple(ITEM_TITLES.values())


def dungeon_definition(original):
    """Project approved dungeon effects without changing the pinned catalog."""
    title = original['m_iTitleID']
    if title not in TITLE_IDS:
        return original
    index = TITLE_IDS.index(title)
    options = (99233, 43706, 20305, 200400 + index,
               200410 + index * 3, 200411 + index * 3, 200412 + index * 3)
    return dict(original, m_iAtkPhysic=0, m_iAtkMagic=0,
                SOCKET_OPTION={str(i): value for i, value in enumerate(options, 1)})


def offers():
    return tuple(dict(sku=1_200_000_000 + item, template=item,
                      name=client_data().item(item)['name'], category=32,
                      price=PRICE_ED, quantity=1)
                 for item in ITEM_TITLES)
