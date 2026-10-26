"""Pure A0A static KIM selector from original 6CFB80/2CE9730.

This never authorizes an offer or an economic operation. The caller owns real
listing/cache membership, template-ID selection, name matching and every
instance/context predicate. D3 is a class code, not character/item level.
"""
from dataclasses import dataclass
import struct

_BASE_CATEGORY = {1:1,2:1,3:2,5:6,6:3,7:4,8:5,11:4,12:4,13:4,14:4,15:21,16:25}
_CATEGORIES = frozenset((0,1,2,3,4,5,6,7,21,25,27,32,33))


def native_category(flags4, flags8):
    """Exact original 2CE9730 classifier; 255 means no recognized category."""
    for value in (flags4, flags8):
        if type(value) is not int or not 0 <= value < 2**32:
            raise ValueError('Exact u32 KIM flags required')
    bucket = (flags8 >> 3) & 31
    if flags4 & 1:
        if flags8 & 0x100:
            return 33 if bucket == 3 else 27
        return 32 if bucket == 3 else 7
    if bucket == 3 and flags8 & 0x100:
        return 33
    return _BASE_CATEGORY.get(bucket, 255)


@dataclass(frozen=True)
class NativeTemplateFacts:
    template: int
    flags4: int
    flags8: int
    native_category: int
    slot: int
    grade: int
    unit_type: int
    unit_class_code: int
    item_type_bucket: int
    dual_unit_bit: bool
    static_query_gate: bool


def facts_from_item(item):
    """Extract only fields directly consumed by the native static predicate."""
    raw = item['record']
    if type(raw) is not bytes or len(raw) != 232:
        raise ValueError('Exact current 232-byte KIM record required')
    template, flags4, flags8 = struct.unpack_from('<iII', raw)
    if type(item['id']) is not int or template <= 0 or template != item['id']:
        raise ValueError('KIM identity mismatch')
    if item['flags4'] != flags4 or item['flags8'] != flags8:
        raise ValueError('KIM flags mismatch')
    bucket = (flags8 >> 3) & 31
    gate = (not(flags4 & 2) or raw[0xd7] != 0) and not(flags4 & 32) and bucket != 9
    return NativeTemplateFacts(template, flags4, flags8, native_category(flags4,flags8),
                               raw[0xd5], (flags4 >> 20) & 15, raw[0xd2], raw[0xd3],
                               bucket, bool(flags8 & 4), bool(gate))


def catalog_facts(template, catalog=None):
    if type(template) is not int or not 0 < template < 2**31:
        raise ValueError('Exact template ID required')
    if catalog is None:
        from els_server.game_data import client_data
        catalog = client_data()
    return facts_from_item(catalog.item(template))


@dataclass(frozen=True)
class NativeStaticSelector:
    category: int = 0
    dual_unit_mode: int = 255
    slots: tuple = ()                # A0A DTO+12
    grades: tuple = ()               # +22
    unit_types: tuple = ()           # +32
    unit_class_codes: tuple = ()     # +42, native u16 set vs KIM byte D3
    item_type_buckets: tuple = ()    # +52

    def __post_init__(self):
        if type(self.category) is not int or self.category not in _CATEGORIES:
            raise ValueError('Unqualified native category')
        if type(self.dual_unit_mode) is not int or self.dual_unit_mode not in (0,1,255):
            raise ValueError('Unqualified dual-unit mode')
        for name, upper in (('slots',256),('grades',256),('unit_types',256),
                            ('unit_class_codes',65536),('item_type_buckets',256)):
            values = getattr(self,name)
            if type(values) is not tuple or any(type(v) is not int or not 0 <= v < upper for v in values):
                raise ValueError('Canonical native integer tuple required')
            if values != tuple(sorted(set(values))):
                raise ValueError('Canonical native ordered set required')


def matches_static(facts, selector):
    """Exact A0A static slice; does not replace cache/name/context/instance gates."""
    if type(facts) is not NativeTemplateFacts or type(selector) is not NativeStaticSelector:
        raise ValueError('Exact native facts and selector required')
    if not facts.static_query_gate:
        return False
    if selector.category and facts.native_category != selector.category:
        return False
    for chosen, actual in ((selector.slots,facts.slot),(selector.grades,facts.grade),
                           (selector.unit_types,facts.unit_type),
                           (selector.unit_class_codes,facts.unit_class_code),
                           (selector.item_type_buckets,facts.item_type_bucket)):
        if chosen and actual not in chosen:
            return False
    # 6CFB80 gates the split bit ONLY for unit type10. 6D0060 differs here;
    # the latter must not be silently substituted for this A0A predicate.
    if facts.unit_type == 10 and selector.dual_unit_mode != 255:
        if int(facts.dual_unit_bit) != selector.dual_unit_mode:
            return False
    return True
