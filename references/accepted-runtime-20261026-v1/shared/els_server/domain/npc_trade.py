"""Merchant stock and integer ED prices from the pinned original resources."""
import functools
import hashlib
import json
import struct
from els_server.paths import PROJECT_ROOT
from els_server.game_data import client_data
from els_server.domain.inventory_items import VERIFIED_TEMPLATES
from els_server.domain.acquisition_policy import require_acquirable


@functools.lru_cache(maxsize=1)
def stock():
    root = PROJECT_ROOT/'analysis/sol-high-20261015/npc-bank-box'
    raw = (root/'ShopItem.lua.tables.json').read_bytes()
    manifest = json.loads((PROJECT_ROOT/'els_server/data/npc_trade.manifest.json').read_text(encoding='utf8'))
    if hashlib.sha256(raw).hexdigest() != manifest['tables_sha256']:
        raise ValueError('Merchant stock evidence changed')
    result = {}
    for call in json.loads(raw)['__symbolic_calls__']:
        if call['function'] != 'g_pItemManager.AddShopItemList_LUA':
            continue
        row = call['arguments'][1]
        for npc in row.get('SALE_ITEM_NPC', {}).values():
            if not isinstance(npc, dict):
                continue
            target = result.setdefault((row['VILLIAGE_ID'], npc['NPC_ID']), set())
            # This client is the international build. KR-exclusive lists do
            # not become purchasable merely because they share an archive.
            for key in ('ITEM_LIST', 'ITEM_LIST_INT'):
                target.update(t for t in npc.get(key, {}).values() if type(t) is int and t > 0)
    return {k: frozenset(v) for k, v in result.items()}


def price(template, repurchase=False):
    row = client_data().item(template)
    ed, vp = struct.unpack_from('<ii', row['record'], 0x1c)
    # VP balance persistence is not implemented. A mixed ED/VP offer must not
    # silently lose its second currency or be sold at its ED component alone.
    if not 0 < ed < 2**31 or (vp != 0 and not repurchase):
        raise ValueError('Merchant price/currency is unavailable')
    return ed


def offer(town, merchant, template):
    if template not in stock().get((town, merchant), ()) or template not in VERIFIED_TEMPLATES:
        raise ValueError('Item is not an admitted offer of this town merchant')
    require_acquirable(template)
    return price(template)
