"""Current ordinary alchemist AP offers from the original merchant and item tables."""
from functools import lru_cache
import struct

from els_server.domain.camilla_ap_shop import Offer

_RECOVERY = frozenset((77420, 77430, 710033))
_TEMPLATES = _RECOVERY | {109945, 109955}


@lru_cache(maxsize=1)
def _offers():
    from els_server.game_data import client_data

    offers = {}
    for template in _TEMPLATES:
        raw = client_data().item(template)['record']
        ed, ap = struct.unpack_from('<ii', raw, 0x1c)
        if ed < 0 or ap <= 0 or raw[0xd0] or raw[0xd2] or raw[0xe1]:
            raise ValueError('Alchemist AP price or eligibility changed')
        offers[template] = Offer(ed, ap, 0, 0)
    return offers


def catalog(town, merchant):
    from els_server.domain.npc_trade import stock

    if town not in range(20001, 20014):
        return {}
    templates = stock().get((town, merchant), ())
    if not _RECOVERY.issubset(templates):
        return {}
    return {t: price for t, price in _offers().items() if t in templates}
