"""Local playability clamp for imported public NPC HP.

Why this exists
---------------
``els_server/data/formal_npc_hp.json`` imports absolute maximum HP from a public
database whose source rows describe a later retail generation than this client.
Measured against a level-appropriate character of this build the imported values
run 5 to 9 orders of magnitude too high: the Devildom 6 street boss imports as
121,147,015,168 HP and the Devildom 7 raid boss as 199,692,877,037,568 HP, while
a fully geared Lv99 character of this client produces roughly 1e5 attack.

What it does
------------
For each map it derives one compression factor and applies it to every imported
maximum of that map. The factor keeps the imported data's *relative* ordering
inside one map and only rescales the absolute magnitude onto the region/role
profile curve that the upstream code already used for maps without imported
data. The factor is capped at 1.0, so maps whose imported values are already
plausible (for example Ruben's 4608 HP) pass through untouched.

What it never touches
---------------------
Explicit client values (``current_client_explicit`` / INIT_COMPONENT MAX_HP)
and the profile-curve fallback itself. Only imported values are compressed, so
there is no feedback loop.

Disable by deleting ``config/local_hp_curve.json`` or setting ``enabled`` false.
"""
import functools
import json
import math
import struct

from els_server.paths import PROJECT_ROOT

CONFIG = PROJECT_ROOT / 'config/local_hp_curve.json'


def f32(value):
    value = struct.unpack('<f', struct.pack('<f', value))[0]
    if not math.isfinite(value):
        raise ValueError('Local HP curve float32 bound')
    return value


@functools.lru_cache(maxsize=1)
def rules():
    try:
        rule = json.loads(CONFIG.read_bytes())
    except FileNotFoundError:
        return {'enabled': False, 'target_scale': 1.0, 'global_scale': 1.0}
    if rule.get('schema_version') != 1 or rule.get('provenance') != 'local_playability_curve':
        raise ValueError('Local HP curve identity')
    if type(rule.get('enabled')) is not bool:
        raise ValueError('Local HP curve switch')
    scale = rule.get('target_scale', 1.0)
    if type(scale) not in (int, float) or not math.isfinite(scale) or not 0.01 <= scale <= 100:
        raise ValueError('Local HP curve target scale')
    overall = rule.get('global_scale', 1.0)
    if type(overall) not in (int, float) or not math.isfinite(overall) or not 0.001 <= overall <= 100:
        raise ValueError('Local HP curve global scale')
    return {'enabled': rule['enabled'], 'target_scale': float(scale), 'global_scale': float(overall)}


def global_scale():
    """One knob for every NPC maximum, imported or not."""
    rule = rules()
    return rule['global_scale'] if rule['enabled'] else 1.0


def _anchor(dungeon):
    """Largest imported maximum this map can hand out, or None when it imports none."""
    from els_server.domain import formal_npc_hp as source
    row = source.policy()['maps'].get(str(dungeon))
    if row is None:
        return None
    values = [item['hp_float32'] for item in (row.get('public_hp_templates') or {}).values()
              if item.get('hp_float32') and item['hp_float32'] > 0]
    raid = source.raid_policy()['maps'].get(str(dungeon))
    if raid is not None:
        values.extend(item['hp'] for item in (raid.get('templates') or {}).values()
                      if item.get('hp') and item['hp'] > 0)
    return max(values) if values else None


def _target(dungeon):
    """Region/role profile HP for this map's strongest monster."""
    from els_server.domain import formal_npc_hp as source
    data = source.policy()
    row = data['maps'][str(dungeon)]
    profile = data['profiles'].get(str(row['region']) + ':boss', data['profiles']['default:boss'])
    return f32(f32(profile['base']) + f32(f32(profile['growth']) * f32(row['level'])))


@functools.lru_cache(maxsize=None)
def factor(dungeon):
    rule = rules()
    if not rule['enabled']:
        return 1.0
    anchor = _anchor(dungeon)
    if anchor is None or anchor <= 0:
        return 1.0
    target = _target(dungeon) * rule['target_scale']
    if not target > 0:
        return 1.0
    return min(1.0, f32(target / anchor))


def apply(dungeon, maximum):
    """Curve compression plus the global gate. Idempotent per (map, value)."""
    value = f32(maximum)
    if value <= 0:
        return value
    rule = rules()
    if not rule['enabled']:
        return value
    scale = f32(factor(dungeon) * rule['global_scale'])
    if scale == 1.0:
        return value
    scaled = f32(value * scale)
    # Never hand a non-positive maximum to the initializer.
    return scaled if scaled > 0 else value


def report(dungeons):
    """Diagnostics for the maps the caller cares about."""
    rows = []
    for dungeon in dungeons:
        scale = factor(dungeon)
        anchor = _anchor(int(dungeon))
        rows.append(dict(dungeon=int(dungeon), factor=scale, anchor=anchor,
                         target=_target(int(dungeon))))
    return rows
