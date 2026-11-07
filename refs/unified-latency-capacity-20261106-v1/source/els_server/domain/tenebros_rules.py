"""Finite native shadow IDs; explicit 2026-10-24 local random policy.

Effects remain client-owned. This module validates IDs and chooses native IDs;
it does not calculate or simulate their effects, UI, or timing.
"""
import functools, hashlib, json
from pathlib import Path
from els_server.game_data import CLIENT_SHA, client_data

NORMAL_WEIGHTS = (10,9,8,7,6,5,4,3,2,1)
BLESSED_WEIGHTS = tuple(reversed(NORMAL_WEIGHTS))
ORDINARY_SCROLLS = (118261,118260,118259,118258)
BLESSED_SCROLL = 118323

@functools.lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/tenebros_native.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='18220032e7afca6fdeb560dd31e0e493b35bc22b0a971e2df82753368334de46':
        raise ValueError('Tenebros finite source changed')
    c=json.loads(raw)
    if c['client_sha256']!=CLIENT_SHA or c['catalog_sha256']!=client_data().manifest['catalog_sha256']:
        raise ValueError('Tenebros client/catalog mismatch')
    return c

def supports(template):
    return type(template) is int and str(template) in catalog()['templates']

def template_info(template):
    if not supports(template):raise ValueError('Outside native Tenebros scope')
    row=catalog()['templates'][str(template)]
    if hashlib.sha256(client_data().item(template)['record']).hexdigest()!=row['record_sha256']:
        raise ValueError('Tenebros target record changed')
    return row

def option_info(option):
    if type(option) is not int or str(option) not in catalog()['options']:
        raise ValueError('Unknown native Tenebros option')
    return catalog()['options'][str(option)]

def type_options(type_id):
    if type(type_id) is not int or str(type_id) not in catalog()['types']:
        raise ValueError('Unknown native Tenebros effect type')
    return list(catalog()['types'][str(type_id)]['options'])

def validate(template, values):
    row=template_info(template)
    if not isinstance(values,(list,tuple)) or len(values)!=3 or any(type(v) is not int or v not in row['values'][i] for i,v in enumerate(values)):
        raise ValueError('Invalid native Tenebros option slots')
    return list(values)

def require_identified(item):
    if supports(item['template']):validate(item['template'],item.get('option_groups',{}).get('25',[]))

def weighted(values, roll, *, blessed=False):
    weights=BLESSED_WEIGHTS if blessed else NORMAL_WEIGHTS
    if type(roll) is not int or not 0<=roll<sum(weights) or len(values)!=10:
        raise ValueError('Tenebros value draw range')
    for value,weight in zip(values,weights):
        if roll<weight:return value
        roll-=weight
    raise ValueError('Tenebros value weight total')

def draw_type(template, line, type_id, roll):
    row=template_info(template)
    if type(line) is not int or line not in (0,1,2) or type(type_id) is not int or type_id not in row['types'][line]:
        raise ValueError('Tenebros effect type outside target line')
    return weighted(type_options(type_id),roll)

def draw_initial(template, line, type_roll, tier_roll, blessed=False):
    row=template_info(template)
    if type(line) is not int or line not in (0,1,2):raise ValueError('Tenebros initial line')
    types=row['types'][line]
    if type(type_roll) is not int or not 0<=type_roll<len(types) or type(blessed) is not bool:
        raise ValueError('Tenebros initial type draw')
    return weighted(type_options(types[type_roll]),tier_roll,blessed=blessed)

def load_quote():
    c=catalog()['native_config']
    return c['DefaultCost'],{r['1']:r['2'] for r in c['EssentialItem'].values()}
