"""Fold the local ERP allocation into the seven native combat inputs.

``els_server/data/resonance2026-stats.json`` documents one row per allocation
stat with a ``per_point`` source value, and states outright that those numbers
are "per-point numbers preserved as source values, not applied combat formulas".
Nothing on the server applied them, so a fully invested character logged in with
exactly the same attack as a naked one.

The seven-field layout is HP / physical attack / magical attack / retained /
retained / physical defense / magical defense (see character_stats docstring),
so only three rows have a slot:

    1  ERT_ALL_ATK_ABS   flat attack   -> +per_point per point into slots 1 and 2
    2  ERT_ALL_DEF_ABS   flat defense  -> +per_point per point into slots 5 and 6
    16 ERT_MAX_HP_REL    percent HP    -> scale slot 0

The remaining rows have no wire slot at all:

    4  element resistance, 17 max MP       -> dropped, nothing to carry them
    18 skill damage %, 19 polarization,
    20 boss damage %                       -> dungeon-only multiplicative
                                              damage modifiers

Those three are folded into the attack inputs as an explicit LOCAL
APPROXIMATION so a dungeon page full of points still moves damage. This is not
the retail formula: it also lifts non-skill hits, and polarization is not really
a linear percentage. It is applied because the alternative observed in play was
"the panel shows +35% and the damage never changes".
"""
import functools
import json
import struct
from pathlib import Path

from els_server.game_data import CLIENT_SHA
from els_server.paths import PROJECT_ROOT

RULE_PATH = PROJECT_ROOT / 'els_server/data/resonance2026-stats.json'

ATTACK_STATS = (1,)
DEFENSE_STATS = (2,)
MAX_HP_STATS = (16,)
# Multiplicative damage rows with no field of their own; see module docstring.
FOLDED_DAMAGE_STATS = (18, 19, 20)


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


@functools.lru_cache(maxsize=1)
def rules():
    raw = RULE_PATH.read_bytes()
    row = json.loads(raw)
    if (row['schema'] != 1
            or row['client_sha256'] != CLIENT_SHA
            or len(row['rows']) != 15):
        raise ValueError('Unreviewed ERP stat table')
    table = {}
    for entry in row['rows']:
        stat = entry['stat_id']
        if type(stat) is not int or stat in table:
            raise ValueError('Duplicate ERP stat identity')
        per_point = entry['per_point']
        if type(per_point) is not int and type(per_point) is not float:
            raise ValueError('ERP per-point value')
        table[stat] = entry
    for stat in ATTACK_STATS + DEFENSE_STATS + MAX_HP_STATS + FOLDED_DAMAGE_STATS:
        if stat not in table:
            raise ValueError('Missing reviewed ERP stat row: %d' % stat)
    return table


def apply(values, character):
    """Return *values* with the selected page's allocation folded in."""
    if character is None:
        return values
    allocation = character.get('resonance_allocation')
    if not allocation:
        return values
    table = rules()
    flat_attack = sum(table[s]['per_point'] * allocation.get(s, 0) for s in ATTACK_STATS)
    flat_defense = sum(table[s]['per_point'] * allocation.get(s, 0) for s in DEFENSE_STATS)
    hp_scale = 1.0 + sum(table[s]['per_point'] * allocation.get(s, 0) / 100.0
                         for s in MAX_HP_STATS)
    damage_scale = 1.0 + sum(table[s]['per_point'] * allocation.get(s, 0) / 100.0
                             for s in FOLDED_DAMAGE_STATS)
    out = list(values)
    out[0] = f32(out[0] * hp_scale)
    out[1] = f32((out[1] + flat_attack) * damage_scale)
    out[2] = f32((out[2] + flat_attack) * damage_scale)
    out[5] = f32(out[5] + flat_defense)
    out[6] = f32(out[6] + flat_defense)
    return out
