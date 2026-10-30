"""Upper bound for imported retail-scale maximum HP on pinned local maps.

The Master Road family (``Dungeon_Md_*``, 34370-34700) imports absolute maximum
HP from a later retail generation: its bosses arrive at 505,514,880 through
15,554,304,000 HP while this client's Lv99 character deals roughly 1e5 damage
per hit, so no local session can kill them. Ordinary mobs of the same maps
import 119,702 / 432,064 / 30,000 and are already playable.

This overlay caps each maximum of a listed map at the region/role boss profile
value (113,340 + 17,005.6 x level = 1,796,894.375 at Lv99) times that map's
multiplier. Values below the cap pass through untouched, so the imported
relative ordering inside one map survives and the already working 34490 keeps
its exact current numbers.

Only maps listed in ``config/local_boss_hp_cap.json`` are touched. Delete the
file or set ``enabled`` false to restore the raw imports.
"""
import functools
import json
import math
import struct

from els_server.paths import PROJECT_ROOT

CONFIG = PROJECT_ROOT / 'config/local_boss_hp_cap.json'
PROVENANCE = 'local_boss_hp_cap'


def f32(value):
    value = struct.unpack('<f', struct.pack('<f', value))[0]
    if not math.isfinite(value):
        raise ValueError('Local boss cap float32 bound')
    return value


@functools.lru_cache(maxsize=1)
def rules():
    try:
        rule = json.loads(CONFIG.read_bytes())
    except FileNotFoundError:
        return {'enabled': False, 'maps': {}}
    if rule.get('schema_version') != 1 or rule.get('provenance') != PROVENANCE:
        raise ValueError('Local boss cap identity')
    if type(rule.get('enabled')) is not bool:
        raise ValueError('Local boss cap switch')
    rows = rule.get('maps')
    if type(rows) is not dict:
        raise ValueError('Local boss cap map table')
    maps = {}
    for key, multiplier in rows.items():
        if not key.isdigit() or int(key) <= 0:
            raise ValueError('Local boss cap map identity')
        if (type(multiplier) not in (int, float) or not math.isfinite(multiplier)
                or not 0.01 <= multiplier <= 100):
            raise ValueError('Local boss cap multiplier bound')
        maps[int(key)] = float(multiplier)
    return {'enabled': rule['enabled'], 'maps': maps}


@functools.lru_cache(maxsize=None)
def target(dungeon):
    """Region/role profile maximum at this map's own level."""
    from els_server.domain import formal_npc_hp as source
    data = source.policy()
    row = data['maps'].get(str(dungeon))
    if row is None:
        raise ValueError('Local boss cap map is not an imported NPC HP map')
    profile = data['profiles'].get(str(row['region']) + ':boss', data['profiles']['default:boss'])
    return f32(f32(profile['base']) + f32(f32(profile['growth']) * f32(row['level'])))


def apply(dungeon, maximum):
    """Cap an imported maximum at the map's boss target. Idempotent."""
    rule = rules()
    if not rule['enabled']:
        return maximum
    multiplier = rule['maps'].get(dungeon)
    if multiplier is None:
        return maximum
    value = f32(maximum)
    if value <= 0:
        return maximum
    limit = f32(target(dungeon) * multiplier)
    return value if value <= limit else limit
