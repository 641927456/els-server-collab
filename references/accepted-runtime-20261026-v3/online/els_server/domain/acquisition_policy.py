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


# Historical CN2020 ticket compatibility: decode/consume existing saves only.
# Current normal acquisition is unverified; all existing grant gates reject these.
LEGACY_USE_ONLY_TICKETS = frozenset((711338,711339,711340,711341,711342,711343,118640,118641,118642,118657,118658,118659))

# Finite Cartridge admission is for existing singleton instances only. Adding
# their reader definitions must not implicitly enable any new generic grant.
CARTRIDGE_USE_ONLY_MATERIALS = frozenset((
    119222,119223,119224,119225,119226,119227,119228,119229,119230,
    119231,119232,119233,119234,119235,119236,119237,119238,119239,119240))


# Exact CN includes-Lithia generation7 tickets: existing owned use only.
# No current normal source is qualified; keep all new grant paths closed.
LITHIA_GEN7_USE_ONLY_TICKETS = frozenset((718388,718389,718390,718391,718392,718393))

# Exact CN historical page1 variants: existing owned use for enumerated roles1..9 targets only.
# All other targets/roles and every new grant stay closed; no full-ticket range claim.
HISTORICAL_PAGE1_USE_ONLY_TICKETS = frozenset((713172,713173,713174,713175,713176,713177,713438,713439,713440,713441,713442,713443))

def can_acquire(template,*,cartridge_box_source=None,cartridge_select_source=None,cartridge_recipe679_source=None,raid_reward_source=None,silver_source=None,daily_special_source=None):
    from els_server.domain.silver_mirror_catalog import INVITATIONS
    if template in INVITATIONS:return False
    if silver_source is not None:
        if any(v is not None for v in(cartridge_box_source,cartridge_select_source,cartridge_recipe679_source,raid_reward_source,daily_special_source)):raise ValueError('Incompatible Mirror acquisition sources')
        from els_server.domain.silver_mirror_rewards import validate_source
        return validate_source(silver_source).admit_template(template)
    if template==30870:return False
    daily_shared=False
    if daily_special_source is not None:
        if any(v is not None for v in(cartridge_box_source,cartridge_select_source,cartridge_recipe679_source,raid_reward_source)):raise ValueError('Incompatible daily acquisition sources')
        from els_server.storage.ariel_daily_special import validate_source as daily_source
        daily_shared=daily_source(daily_special_source).validate_template(template)
    if raid_reward_source is not None:
        if any(v is not None for v in(cartridge_box_source,cartridge_select_source,cartridge_recipe679_source)):raise ValueError('Incompatible raid acquisition sources')
        from els_server.domain.raid_reward_items import validate_source
        validate_source(raid_reward_source).validate_template(template)
    from els_server.domain.raid_reward_items import source_only_templates
    if template in source_only_templates()and raid_reward_source is None and not daily_shared:return False
    if template in(190401,310775,310776,722760,722761):return False  # Original owned economic elixirs only.
    if template in(310777,722762,722990):return False  # Existing owned native battle elixirs only.
    if template in(135952,135954,135955):return False  # Current owned life potion aliases only.
    if template in(715920,718310):return False  # Original owned teacher bundles only.
    if template==715036:return False  # Existing owned box only; no grant source exception.
    qualified=raid_reward_source is not None
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
    if template==119216 and raid_reward_source is None:return False
    if template in HISTORICAL_PAGE1_USE_ONLY_TICKETS:return False
    if template in LITHIA_GEN7_USE_ONLY_TICKETS:return False
    if template in LEGACY_USE_ONLY_TICKETS:return False
    if template in CARTRIDGE_USE_ONLY_MATERIALS and not qualified:return False
    from els_server.domain.ordinary_accessories import definitions
    accessory=definitions().get(template)
    return template not in excluded_equipment() and not (accessory and accessory['compatibility_only']and raid_reward_source is None)


def require_acquirable(template,*,cartridge_box_source=None,cartridge_select_source=None,cartridge_recipe679_source=None,raid_reward_source=None,silver_source=None,daily_special_source=None):
    if not can_acquire(template,cartridge_box_source=cartridge_box_source,cartridge_select_source=cartridge_select_source,cartridge_recipe679_source=cartridge_recipe679_source,raid_reward_source=raid_reward_source,silver_source=silver_source,daily_special_source=daily_special_source):
        raise ValueError(f'Legacy equipment acquisition disabled: {template}')
