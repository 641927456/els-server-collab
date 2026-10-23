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

# Reset variants remain existing-inventory use only; no new source.
LEGACY_USE_ONLY_TICKETS = frozenset((118640,118641,118642,118657,118658,118659))


def can_acquire(template,*,cartridge_box_source=None,cartridge_select_source=None,cartridge_recipe679_source=None):
    if template in LEGACY_USE_ONLY_TICKETS:return False
    qualified=False
    recipe_box=False
    if cartridge_recipe679_source is not None:
        if cartridge_box_source is not None or cartridge_select_source is not None:raise ValueError("Incompatible Cartridge sources")
        from els_server.domain.cartridge_recipe679_rules import validate_recipe_source
        validate_recipe_source(cartridge_recipe679_source).consume_template(template)
        recipe_box=True
    if cartridge_box_source is not None and cartridge_select_source is not None:raise ValueError("Incompatible Cartridge sources")
    if cartridge_select_source is not None:
        from els_server.domain.cartridge_exchange_rules import validate_select_source
        validate_select_source(cartridge_select_source).consume_template(template)
        qualified=True
    if cartridge_box_source is not None:
        from els_server.domain.cartridge_selection_box import validate_source
        validate_source(cartridge_box_source).consume_template(template)
        qualified=True
    if template==119335 and not recipe_box:return False
    if template==119216:return False
    if template in CARTRIDGE_USE_ONLY_MATERIALS and not qualified:return False
    from els_server.domain.ordinary_accessories import definitions
    accessory=definitions().get(template)
    return template not in excluded_equipment() and not (accessory and accessory['compatibility_only'])


def require_acquirable(template,*,cartridge_box_source=None,cartridge_select_source=None,cartridge_recipe679_source=None):
    if not can_acquire(template,cartridge_box_source=cartridge_box_source,cartridge_select_source=cartridge_select_source,cartridge_recipe679_source=cartridge_recipe679_source):
        raise ValueError(f'Legacy equipment acquisition disabled: {template}')
