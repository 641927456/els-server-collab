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


@functools.lru_cache(maxsize=1)
def ordinary_grades():
    grades = client_data().resource('Enum.lua')['ITEM_GRADE']
    return frozenset(grades[k] for k in ('IG_UNIQUE', 'IG_ELITE', 'IG_RARE', 'IG_NORMAL', 'IG_LOW'))


def reward_definition(template=701000):
    if template==118445:
        from els_server.domain.white_chip_decomposition import reward_definition as fragment_definition
        return fragment_definition()
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
    from els_server.domain.inventory_items import validate_item
    from els_server.domain.normal_equipment import definitions
    from els_server.domain.npc_sale import unit_price
    from els_server.domain.item_expiration import require_current
    from els_server.domain.item_locks import require_unlocked
    item = validate_item(item)
    require_current(item)
    require_unlocked(item)
    from els_server.domain.white_chip_decomposition import quote as chip_quote
    special=chip_quote(item)
    if special is not None:return special
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
