"""Local override for the client's boss-gauge line count.

The client divides a boss's maximum HP by the gauge line count it receives
(``dungeon_population.py`` records the 1693620 interpolation), and it draws a
Master Road boss as a 151-line gauge. The imported route data declares one line
for every ``Dungeon_Md_*`` boss, so the client's own accounting stalls at
1/1000 of the maximum and the boss never dies.

Only maps listed in ``config/local_boss_gauge.json`` are touched. Delete the
file or set ``enabled`` false to restore the imported line counts.
"""
import functools
import json

from els_server.paths import PROJECT_ROOT

CONFIG = PROJECT_ROOT / 'config/local_boss_gauge.json'
PROVENANCE = 'local_boss_gauge'


@functools.lru_cache(maxsize=1)
def rules():
    try:
        rule = json.loads(CONFIG.read_bytes())
    except FileNotFoundError:
        return {'enabled': False, 'maps': {}}
    if rule.get('schema_version') != 1 or rule.get('provenance') != PROVENANCE:
        raise ValueError('Local boss gauge identity')
    if type(rule.get('enabled')) is not bool:
        raise ValueError('Local boss gauge switch')
    rows = rule.get('maps')
    if type(rows) is not dict:
        raise ValueError('Local boss gauge map table')
    maps = {}
    for key, count in rows.items():
        if not key.isdigit() or int(key) <= 0:
            raise ValueError('Local boss gauge map identity')
        if type(count) is not int or not 1 <= count <= 65535:
            raise ValueError('Local boss gauge line bound')
        maps[int(key)] = count
    return {'enabled': rule['enabled'], 'maps': maps}


def lines(dungeon, imported):
    """Overlay the gauge line count of a listed map. Idempotent."""
    rule = rules()
    if not rule['enabled']:
        return imported
    return rule['maps'].get(dungeon, imported)
