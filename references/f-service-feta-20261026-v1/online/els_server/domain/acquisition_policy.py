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

def can_acquire(template,*,cartridge_box_source=None,cartridge_select_source=None,cartridge_recipe679_source=None,raid_reward_source=None,silver_source=None,daily_special_source=None,regional_cube_source=None,black_market_box_source=None,feta_exchange_source=None):
    if feta_exchange_source is not None:
        if any(x is not None for x in(cartridge_box_source,cartridge_select_source,cartridge_recipe679_source,raid_reward_source,silver_source,daily_special_source,regional_cube_source,black_market_box_source)):raise ValueError('Incompatible Feta acquisition source')
        from els_server.storage.feta_exchange_source import validate_source
        return validate_source(feta_exchange_source).consume_template(template)
    if template==119328:return False  # Reader/consumer is not permission for any generic source.
    if black_market_box_source is not None:
        if any(v is not None for v in(cartridge_box_source,cartridge_select_source,cartridge_recipe679_source,raid_reward_source,silver_source,daily_special_source,regional_cube_source)):raise ValueError('Incompatible market box acquisition source')
        from els_server.domain.black_market_box_rules import validate_source
        return validate_source(black_market_box_source).admit_template(template)
    cube=False
    if regional_cube_source is not None:
        if any(v is not None for v in(cartridge_box_source,cartridge_select_source,cartridge_recipe679_source,raid_reward_source,silver_source,daily_special_source)):
            raise ValueError('Incompatible regional cube acquisition sources')
        from els_server.storage.regional_boss_cube_source import validate_source
        validate_source(regional_cube_source).consume_template(template)
        cube=True
    from els_server.domain.black_market_rules import definitions as black_market_readers
    from els_server.domain.black_market_box_rules import catalog as market_boxes
    if template!=119335 and template in {r['template']for r in (*black_market_readers(),*market_boxes()['inner_readers'])if not r['already_registered']}:return False
    from els_server.domain.silver_mirror_catalog import INVITATIONS
    if template in INVITATIONS:return False
    if silver_source is not None:
        if any(v is not None for v in(cartridge_box_source,cartridge_select_source,cartridge_recipe679_source,raid_reward_source,daily_special_source)):raise ValueError('Incompatible Mirror acquisition sources')
        from els_server.domain.silver_mirror_rewards import validate_source
        return validate_source(silver_source).admit_template(template)
    if template in (307689, 316095, 316096, 328301, 328302, 328303, 328304, 328305, 328306, 328307, 328308, 328309, 328310, 328311, 328312, 328313, 328314, 328315, 333343, 334713, 715242, 715243, 715244, 715245, 715246, 715247, 715248, 715249, 715250, 715251, 715252, 715253, 715254, 715255, 715256, 716740, 716741, 716742, 716743, 716744, 716745, 716746, 716747, 716748, 716749, 716750, 716751, 716752, 716753, 716754, 717846):return False  # Owned assembly uniforms; no new source.
    if template in(100005719,100005720,100005721,100005722):return False  # Existing owned wisdom potions only.
    if template in (77200, 77201, 154118, 166610, 168348, 189209, 190393, 190398, 297093, 297761, 710096, 710097, 710099, 710100, 710101, 710102, 710103, 110004219):return False  # Retained ordinary-fatigue inventory only.
    if template==303673:return False  # Existing owned potion selection box only.
    if template==60008058:return False  # Approved current native effect for owned legacy singleton only.
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
    return template not in excluded_equipment() and (cube or not (accessory and accessory['compatibility_only']and raid_reward_source is None))


def require_acquirable(template,*,cartridge_box_source=None,cartridge_select_source=None,cartridge_recipe679_source=None,raid_reward_source=None,silver_source=None,daily_special_source=None,regional_cube_source=None,black_market_box_source=None,feta_exchange_source=None):
    if not can_acquire(template,cartridge_box_source=cartridge_box_source,cartridge_select_source=cartridge_select_source,cartridge_recipe679_source=cartridge_recipe679_source,raid_reward_source=raid_reward_source,silver_source=silver_source,daily_special_source=daily_special_source,regional_cube_source=regional_cube_source,black_market_box_source=black_market_box_source,feta_exchange_source=feta_exchange_source):
        raise ValueError(f'Legacy equipment acquisition disabled: {template}')
