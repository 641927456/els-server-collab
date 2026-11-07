"""Documented base growth inputs, separate from native equipment/effect math.

This is not a recovered native naked-growth function. Source provenance stays
explicit until a current native/retail baseline independently qualifies it.
"""
import functools,json,math,struct
from pathlib import Path
from els_server.game_data import CLIENT_SHA,client_data

RULE_PATH=Path(__file__).resolve().parents[2]/'config/combat_rules.json'

def f32(v):return struct.unpack('<f',struct.pack('<f',v))[0]

@functools.lru_cache(maxsize=1)
def rules():
    rule=json.loads(RULE_PATH.read_bytes())
    if (rule['schema_version']!=2 or rule['provenance']!='documented_growth_native_inputs'
        or rule['client_sha256']!=CLIENT_SHA or rule['initial_unit_types']!=list(range(1,16))
        or rule['level_min']!=1 or rule['level_max']!=99):raise ValueError('Base source identity')
    for name in ('base_attributes','level_increments'):
        row=rule[name]
        if len(row)!=7 or any(type(v)not in(int,float)or not math.isfinite(v)or v<0 for v in row):raise ValueError('Base source vector')
    if rule['base_attributes']!=[10000,320,320,0,0,80,80] or rule['level_increments']!=[1500,9,9,0,0,2.25,2.25]:raise ValueError('Base sourced rule changed')
    from els_server.domain.character_stats import _tables
    table=_tables()['CHARACTER_RELATIVE_STAT_TABLE']
    if any(tuple(table[t])!=tuple(rule['initial_reference']) for t in rule['initial_unit_types']):raise ValueError('Base initial-client reference changed')
    return rule

def values(character=None):
    rule=rules()
    if character is None:return tuple(map(float,rule['base_attributes']))
    if type(character)is not dict or type(character.get('unit_class'))is not int or ('unit_type'in character and type(character['unit_type'])is not int):raise ValueError('Base role identity')
    unit=client_data().unit(character['unit_class'])
    if unit['unitType']not in rule['initial_unit_types'] or character.get('unit_type',unit['unitType'])!=unit['unitType']:raise ValueError('Base role identity')
    level=character['level']
    if type(level)is not int or not rule['level_min']<=level<=rule['level_max']:raise ValueError('Base level bound')
    return tuple(f32(base+(level-1)*increment)for base,increment in zip(rule['base_attributes'],rule['level_increments']))
