"""Local acquisition policy requested by the owner; not a retail drop table.

Keep legacy definitions available to decode and operate existing inventory.
Only new grants and offer/pool membership are restricted here.
"""
import functools
import re
import unicodedata
from els_server.game_data import client_data


def has_legacy_marker(name):
    # Match the explicit marker, not ordinary words such as 破旧 or 怀旧.
    return bool(re.search(r'\(\s*[旧舊]\s*\)', unicodedata.normalize('NFKC', name)))


@functools.lru_cache(maxsize=1)
def excluded_equipment():
    with client_data().connect() as db:
        return frozenset(t for t, name in db.execute(
            'SELECT id,name FROM items WHERE item_type IN (1,2,3)') if has_legacy_marker(name))


CARTRIDGE_USE_ONLY_MATERIALS = frozenset((
    119222,119223,119224,119225,119226,119227,119228,119229,119230,
    119231,119232,119233,119234,119235,119236,119237,119238,119239,119240))

def can_acquire(template):
    if template in CARTRIDGE_USE_ONLY_MATERIALS:return False
    from els_server.domain.ordinary_accessories import definitions
    accessory=definitions().get(template)
    return template not in excluded_equipment() and not (accessory and accessory['compatibility_only'])


def require_acquirable(template):
    if not can_acquire(template):
        raise ValueError(f'Legacy equipment acquisition disabled: {template}')
