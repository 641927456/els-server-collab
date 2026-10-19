"""Native equipment-relative stats plus separately labelled local base stats.

The seven-field layout is HP, physical attack, magical attack, two retained
fields, physical defense, magical defense. Relative table columns are reordered
exactly as B6F800; B6F9C0 and private-output comparisons verify the arithmetic.
No evaluation of arbitrary client Lua is performed.
"""
import functools
import json
import math
import struct
from els_server.game_data import client_data
from els_server.paths import PROJECT_ROOT


def f32(value):return struct.unpack('<f',struct.pack('<f',value))[0]


@functools.lru_cache(maxsize=1)
def _parameters():
    data=client_data()
    with data.connect() as db:
        code=json.loads(db.execute("SELECT bytecode_json FROM resources WHERE name='CharacterStatTable.lua'").fetchone()[0])
    # Constants are data; changes require a new native comparison for this
    # pinned build, rather than silently interpreting a different formula.
    physical=code['prototypes'][0]['knum'];hp=code['prototypes'][1]['knum']
    if physical!=[1,.15,.8,.0225,.5] or hp!=[1,.17,10,1.1,.5]:raise ValueError('Unverified stat formula constants')
    return tuple(physical),tuple(hp)


def relative_attributes(A,B,C,level,bonus):
    if len(A)!=7 or len(B)!=7 or len(C)!=7 or len(bonus)!=6:raise ValueError('Stat array size')
    if type(level) is not int or not 0<=level<=255:raise ValueError('Equipment level')
    if any(not math.isfinite(x) for x in (*A,*B,*C,*bonus)) or A[0]<=0:raise ValueError('Stat parameters')
    one,growth,subtract,subtract_growth,half=_parameters()[0]
    h_one,h_growth,scale,h_ratio,h_half=_parameters()[1]
    out=[0.]*7
    for index,extra in ((1,1),(2,2),(5,3),(6,4)):
        n=level+f32(bonus[extra]+bonus[5])-one
        out[index]=f32(math.floor(((A[index]+A[index]*n*growth)-B[index]*subtract-B[index]*n*subtract_growth)*C[index]+half))
    n=level-h_one
    hp=(A[0]+A[0]*n*h_growth)-B[0]-B[0]*n*h_growth
    hp*=f32(bonus[0]+bonus[5])/scale
    hp*=C[0]
    hp*=B[0]/A[0]*h_ratio
    out[0]=f32(math.floor(hp+h_half))
    return tuple(out)


@functools.lru_cache(maxsize=1)
def _tables():
    raw=client_data().resource('CharacterStatTable.lua')
    def convert(name):
        return {row['1']:tuple(f32(row[str(i)]) if i else 0. for i in (6,2,4,0,0,3,5))
                for row in raw[name].values() if isinstance(row,dict) and '1' in row}
    return {name:convert(name) for name in ('CHARACTER_RELATIVE_STAT_TABLE','SECOND_CLASS_RELATIVE_STAT_TABLE',
                                           'EQIP_POSITION_RELATIVE_STAT_TABLE','TRANSCENDENTAL_EQIP_POSITION_RELATIVE_STAT_TABLE')}


def equipment_attributes(template, character, *, additional_bonus=(0,0,0,0,0,0), owner_level=False):
    from els_server.domain.character_rules import CLASSES
    data=client_data();item=data.item(template)
    if len(additional_bonus)!=6 or any(not math.isfinite(v) for v in additional_bonus):raise ValueError('Equipment bonus vector')
    bonus=tuple(f32(a+b) for a,b in zip(item['stat_bonus'],additional_bonus))
    if not any(bonus):return item['stats']
    unit=data.unit(character['unit_class']);tables=_tables()
    B=tables['CHARACTER_RELATIVE_STAT_TABLE'][unit['unitType']]
    stage=CLASSES[character['unit_class']]['stage']
    A=tables['SECOND_CLASS_RELATIVE_STAT_TABLE'][character['unit_class']] if stage>=2 else B
    item_level=item['record'][0xd1]
    position=item['equip_position']
    positions=tables['TRANSCENDENTAL_EQIP_POSITION_RELATIVE_STAT_TABLE'] if character.get('transcendence') and item_level>69 else tables['EQIP_POSITION_RELATIVE_STAT_TABLE']
    if position not in positions:raise ValueError('Missing native equipment position coefficients')
    level=character['level'] if owner_level or (not item_level and not item['flags4']&16) else item_level
    return relative_attributes(A,B,positions[position],level,bonus)


def instance_attributes(item,character):
    """Current default normal instances; fashion retains the raw template path."""
    from els_server.domain.normal_equipment import definitions
    if item['template'] in definitions():
        from els_server.domain.instance_stats import normal_instance_attributes
        from els_server.domain.equipment_enhancement import validate as validate_enhancement
        enhancement=validate_enhancement(item['template'],item['enhancement']) if 'enhancement' in item else 0
        return normal_instance_attributes(item['template'],character,enhancement=enhancement)
    return equipment_attributes(item['template'],character)


@functools.lru_cache(maxsize=1)
def _base():
    policy=json.loads((PROJECT_ROOT/'config/combat_rules.json').read_text(encoding='utf8'))
    values=policy['base_attributes']
    if policy['schema_version']!=1 or policy['provenance']!='local_policy' or len(values)!=7 or any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in values):raise ValueError('Combat base policy')
    return tuple(values),policy['include_equipment_attributes']


def combat_values(character=None, items=None):
    base,include=_base();values=list(base)
    if character is not None:
        unit=client_data().unit(character['unit_class'])
        if 'unit_type' in character and character['unit_type']!=unit['unitType']:raise ValueError('Combat character template mismatch')
        if include:
            for item in items or ():
                if item['group']==9:
                    from els_server.domain.inventory_items import validate_item
                    validate_item(item)
                    if not equipment_contributes(item,character):continue
                    values=[f32(v+extra) for v,extra in zip(values,instance_attributes(item,character))]
            if items is not None:
                # The server estimate includes the selected title's flat
                # attributes, just as the legacy GetEquippedStat path does.
                # Naked wire inputs omit items and remain unchanged: the
                # native client applies its own equipped title afterward.
                from els_server.domain.titles import attributes as title_attributes
                values=[f32(v+extra) for v,extra in zip(values,title_attributes(character))]
    if any(not math.isfinite(v) or not 0<=v<=1e12 for v in values):raise ValueError('Combat attributes out of bounds')
    return tuple(values)


def equipment_contributes(item,character):
    # An expired item can still be present before the next cleanup tick. Never
    # retain its contribution in authoritative server-side computations.
    from els_server.domain.item_expiration import expired
    if expired(item):return False
    if item['template'] in (92110,92111,92112):
        from els_server.domain.tutorial_accessory import contributes
        return contributes(item,character)
    from els_server.domain.normal_equipment import definitions
    from els_server.domain.equipment_instance import contributes_attributes
    return contributes_attributes(item,character) if item['template'] in definitions() else item['group']==9


def combat_attributes(character=None,items=None):
    # D9B170 B6/D2 and dungeon member attributes are base inputs. Native
    # equipment application adds the equipped map again. Keep server estimates
    # available through combat_values(), but never send them as naked values.
    return struct.pack('>7f',*combat_values(character))


def combat_breakdown(character,items=()):
    """Audit inputs without presenting an equipment reference as naked growth."""
    base=combat_values(character)
    worn=[dict(uid=i['uid'],template=i['template'],attributes=instance_attributes(i,character),
               template_attributes=equipment_attributes(i['template'],character),
               contributes=equipment_contributes(i,character))
          for i in items if i['group']==9]
    unit=client_data().unit(character['unit_class'])
    return dict(level=character['level'],unit_class=character['unit_class'],
                wire_base=base,base_provenance='unverified_local_fallback',
                retail_base_verified=False,level_growth_verified=False,
                equipment=worn,server_base_plus_equipment_estimate=combat_values(character,items),
                native_equipment_reference=_tables()['CHARACTER_RELATIVE_STAT_TABLE'][unit['unitType']],
                equipment_applied_by_native_client=True,
                note='Default normal instance template bonuses and derived fields are included. Naked level growth, set/passive effects and nondefault instances remain unverified; this estimate is not sent as naked attributes.')
