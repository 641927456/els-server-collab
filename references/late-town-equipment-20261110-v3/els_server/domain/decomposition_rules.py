"""Evidence-bounded ordinary dismantling; never substitute for special rewards.

Original 2017 update: one Magical Crystal per 1,000 ED resale value.
Native 198A700 supplies resale value including the current durability ratio.
Fractional crystal rounding and distinct raid/hero reward tables stay closed.
"""
import hashlib
import functools
import json
import struct
from els_server.game_data import client_data
from els_server.paths import PROJECT_ROOT

SOURCE = 'https://elsword.comastuff.com/news/en/13062017_EarlyPhase_EN.pdf'
CIRCUIT_FRAGMENTS_PER_ITEM = 5

# Current ordinary pieces only. Nexon's recovery table lists exactly one
# material for each of these three special dismantling families (help 20050).
SPECIAL_REWARDS = {
    **dict.fromkeys((*range(118262,118318),*range(118372,118376)),118322),
    **dict.fromkeys(range(118332,118336),118331),
    **dict.fromkeys(range(168915,168919),136230),
}


@functools.lru_cache(maxsize=1)
def ordinary_grades():
    grades = client_data().resource('Enum.lua')['ITEM_GRADE']
    return frozenset(grades[k] for k in ('IG_UNIQUE', 'IG_ELITE', 'IG_RARE', 'IG_NORMAL', 'IG_LOW'))


def reward_definition(template=701000):
    if template == 130047:
        from els_server.domain.ice_decomposition import reward_definition as ice_definition
        return ice_definition()
    if template==118445:
        from els_server.domain.white_chip_decomposition import reward_definition as fragment_definition
        return fragment_definition()
    if template in SPECIAL_REWARDS.values() or 30846<=template<=30855:
        item=client_data().item(template)
        return dict(template=template,metadata=item['metadata'],
                    group=3 if item['item_type']==6 else 4,
                    max_stack=struct.unpack_from('<I',item['record'],0x10)[0])
    if template!=701000:raise ValueError('Unqualified decomposition product')
    path = PROJECT_ROOT/'analysis/sol-high-20261015/inventory-sort-lock-decompose/crystal-native.json'
    proof = json.loads(path.read_text(encoding='utf8'))
    row = client_data().item(701000)
    if (proof['record_sha256'] != hashlib.sha256(row['record']).hexdigest()
            or proof['native_reader'] != {'ok': 1, 'consumed': 304}
            or proof['native_group'] != 3 or proof['applied_to_game'] is not False
            or row['metadata'] != 2 or struct.unpack_from('<i', row['record'], 0x10)[0] != 10000):
        raise ValueError('Magical Crystal native evidence mismatch')
    return dict(template=701000, metadata=2, group=3, max_stack=10000)


def quote(item):
    from els_server.domain.abyss_weapon_2026 import weapon_templates
    if item['template'] in weapon_templates():raise ValueError('Event Abyss weapons cannot be dismantled')
    from els_server.domain.inventory_items import validate_item
    from els_server.domain.equipment_circuit_rules import catalog as circuit_catalog
    from els_server.domain.normal_equipment import definitions
    from els_server.domain.npc_sale import unit_price
    from els_server.domain.item_expiration import require_current
    from els_server.domain.item_locks import require_unlocked
    item = validate_item(item)
    require_current(item)
    require_unlocked(item)
    # The ordinary circuit catalog is the finite I/L/T dismantling set.
    if str(item['template']) in circuit_catalog()['materials']:
        if (item['group'] != 1 or item['count'] != 1 or item.get('sealed')
                or 'expires_at' in item or 'activation_seconds' in item):
            raise ValueError('Circuit decomposition requires permanent unsealed bag gear')
        return dict(template=118445, quantity=CIRCUIT_FRAGMENTS_PER_ITEM)
    reward=SPECIAL_REWARDS.get(item['template'])
    if reward is not None:
        if item['group']!=1 or item['count']!=1 or item.get('sealed') or 'expires_at'in item:
            raise ValueError('Special decomposition requires permanent unsealed bag gear')
        return dict(template=reward,quantity=1)
    from els_server.domain.atma_accessories import catalog as atma_catalog
    grade=atma_catalog()['decomposition'].get(str(item['template']))
    if grade is not None:
        if item['group']!=2 or item['count']!=1 or item.get('sealed') or 'expires_at'in item:
            raise ValueError('Atma decomposition requires permanent unsealed bag accessories')
        breath=30846+2*grade
        # Crafted Nirvana accessories return the bound material only.
        reward=dict(template=breath,quantity=1)
        if item['template'] not in range(30816,30846):
            reward['bonus']=breath+1
        return reward
    from els_server.domain.white_chip_decomposition import quote as chip_quote
    special=chip_quote(item)
    if special is not None:return special
    from els_server.domain.ice_decomposition import quote as ice_quote
    special = ice_quote(item)
    if special is not None:
        return special
    if item['group'] != 1 or item['count'] != 1 or item['template'] not in definitions():
        raise ValueError('Ordinary bag equipment required for decomposition')
    row = client_data().item(item['template'])
    raw = row['record']
    # 22937B0 rejects bit5 and requires nonzero +1c for non-cash equipment.
    # High-level/rare special reward families need their own original tables.
    grade = (row['flags4'] >> 20) & 15
    # ITEM_GRADE is deliberately not rarity-sorted in this build:
    # unique=1, elite=2, rare=3, normal=4, low=5, legend=6.
    if row['flags4'] & 0xa1 or row['item_type'] not in (1, 2) or grade not in ordinary_grades() or not 1 <= raw[0xd1] <= 80:
        raise ValueError('Special decomposition rewards not verified')
    # Official 2017 ordinary-equipment rule is expressed in resale ED, not
    # full-durability template value. Ordinary grades use the same rule, excluding
    # distinct reward families above this level band. Do not round fractional
    # crystals or substitute this rule for hero/raid-specific material returns.
    resale = unit_price(item)
    if not 1000 <= resale <= 100000000 or resale % 1000:
        raise ValueError('Fractional crystal rounding not verified')
    return dict(template=701000, quantity=resale//1000, resale_ed=resale,
                input_template=item['template'], record_sha256=hashlib.sha256(raw).hexdigest())
