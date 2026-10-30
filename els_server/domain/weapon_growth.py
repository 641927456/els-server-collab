"""Original Requiem weapon task chain and native growth socket rewards."""
import functools
import json
from pathlib import Path


@functools.lru_cache(maxsize=1)
def catalog():
    return json.loads((Path(__file__).resolve().parents[1]/'data/weapon_growth.json').read_text(encoding='utf8'))


def templates():
    return frozenset(catalog()['templates'])


def quest(completed_stage):
    if type(completed_stage) is not int or not 0<=completed_stage<=5:
        raise ValueError('Weapon growth stage')
    return catalog()['quests'][completed_stage] if completed_stage<5 else None


def options(template,values):
    if template not in templates() or not isinstance(values,list):
        raise ValueError('Unsupported weapon growth options')
    if values and not any(values==row['options'] for row in catalog()['quests']):
        raise ValueError('Invalid weapon growth reward vector')
    return list(values)


def stage(item):
    values=options(item['template'],item.get('option_groups',{}).get('17',[]))
    return next((n for n,row in enumerate(catalog()['quests'],1) if row['options']==values),0)


def eligible_clear(completed_stage,dungeon):
    row=quest(completed_stage)
    return row is not None and dungeon in row['dungeons']
