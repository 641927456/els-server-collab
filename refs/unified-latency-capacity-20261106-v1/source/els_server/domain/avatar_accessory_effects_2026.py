"""Pure projection of original 198A0A0/70F980, using trusted inputs only.

No catalog values or equipment counts are invented here. The caller must
resolve these from original definitions and actual equipped items. This is
not a public request validator, task counter, stat applier or storage writer.
The first record field remains named context2912 until its full lifecycle
is recovered; the second is the client-selected character side.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SetEffects:
    avatar_accessory: bool
    tiers: tuple  # (required_count, effect_id), sorted by count
    variants: tuple  # (required_count, selector, effect_id)

    def __post_init__(self):
        if type(self.avatar_accessory) is not bool:
            raise ValueError('Explicit original avatar flag required')
        for rows, width in ((self.tiers, 2), (self.variants, 3)):
            if type(rows) is not tuple or any(type(row) is not tuple or len(row) != width
                    or any(type(x) is not int or not 0 <= x < 2**31 for x in row)
                    for row in rows):
                raise ValueError('Invalid explicit effect definitions')
        if tuple(sorted(self.tiers, key=lambda row: row[0])) != self.tiers:
            raise ValueError('Original tier ordering required')

    def effects(self, *, selector, count):
        if any(type(x) is not int or not 0 <= x < 2**31 for x in (selector, count)):
            raise ValueError('Invalid equipped-set facts')
        if self.variants:
            return tuple(effect for required, variant, effect in self.variants
                         if selector != 0 and variant == selector and count >= required)
        eligible = tuple(row for row in self.tiers if row[0] <= count)
        if not eligible:
            return ()
        highest = eligible[-1][0]
        return tuple(effect for required, effect in eligible if required == highest)


def project_active_sets(*, records, context2912, side, equipped, definitions):
    """Return active records/effects plus the original filtered set-count map.

    records contain four i32 values in client order. equipped maps set ID to
    (selector, count), definitions maps ID to SetEffects. Both are trusted
    authoritative inputs, not values accepted from the request packet.
    """
    if type(context2912) is not int or not 0 <= context2912 <= 65535:
        raise ValueError('Explicit character context required')
    if type(side) is not int or side not in (0, 1):
        raise ValueError('Explicit character side required')
    if type(records) is not tuple or any(type(row) is not tuple or len(row) != 4
            or any(type(x) is not int or not -2**31 <= x < 2**31 for x in row)
            for row in records):
        raise ValueError('Invalid selection records')
    if type(equipped) is not dict or type(definitions) is not dict:
        raise ValueError('Explicit authoritative maps required')
    for key, facts in equipped.items():
        if type(key) is not int or not 0 < key < 2**31 or type(facts) is not tuple or len(facts) != 2:
            raise ValueError('Invalid equipped set')
        if any(type(x) is not int or not 0 <= x < 2**31 for x in facts):
            raise ValueError('Invalid equipped-set facts')
        if key not in definitions or type(definitions[key]) is not SetEffects:
            raise ValueError('Missing original equipped-set definition')
    remaining = dict(equipped)
    active = []
    for record in records:
        context, selected_side, slot, set_id = record
        if set_id == 0 or context != context2912 or selected_side != side or set_id not in remaining:
            continue
        definition = definitions[set_id]
        if not definition.avatar_accessory:
            continue
        if len(active) == 3:
            del remaining[set_id]
            continue
        selector, count = remaining[set_id]
        effects = definition.effects(selector=selector, count=count)
        if effects:
            active.append((record, count, effects))
    return tuple(active), remaining
