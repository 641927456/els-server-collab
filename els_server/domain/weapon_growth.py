"""Native Requiem, Abyss and Mortal tasks and growth socket rewards."""
import functools
import json
from pathlib import Path


@functools.lru_cache(maxsize=1)
def catalog():
    return json.loads((Path(__file__).resolve().parents[1]/'data/weapon_growth.json').read_text(encoding='utf8'))


@functools.lru_cache(maxsize=1)
def templates():
    return frozenset(t for f in catalog()['families'] for t in f['templates'])


def chain(template):
    return next(f for f in catalog()['families'] if template in f['templates'])


def definition(quest_id):
    return next((q for f in catalog()['families'] for q in f['quests'] if q['id']==quest_id),None)


def preset(template):
    return next((p for p in catalog()['presets'] if p['template']==template),None)


def material_readers():
    from els_server.game_data import client_data
    import hashlib
    for row in catalog()['material_readers']:
        item=client_data().item(row['template'])
        if item['item_type']!=8 or hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']:
            raise ValueError('Native growth material identity')
    return catalog()['material_readers']


def quest(completed_stage,template=136062):
    rows=chain(template)['quests']
    if type(completed_stage) is not int or not 0<=completed_stage<=len(rows):
        raise ValueError('Weapon growth stage')
    return rows[completed_stage] if completed_stage<len(rows) else None


def options(template,values):
    fixed=preset(template)
    if not isinstance(values,list) or template not in templates() and fixed is None:
        raise ValueError('Unsupported weapon growth options')
    if fixed is not None:
        if values and values!=fixed['options']:
            raise ValueError('Invalid preset weapon growth reward vector')
        return list(values)
    if values and not any(values==row['options'] for row in chain(template)['quests']):
        raise ValueError('Invalid weapon growth reward vector')
    return list(values)


def stage(item):
    values=options(item['template'],item.get('option_groups',{}).get('17',[]))
    fixed=preset(item['template'])
    if fixed is not None:return fixed['stage']
    return next((n for n,row in enumerate(chain(item['template'])['quests'],1) if row['options']==values),0)


def eligible_clear(completed_stage,dungeon,template=136062):
    row=quest(completed_stage,template)
    return row is not None and any(dungeon in g.get('dungeons',()) for g in row['objectives'])
