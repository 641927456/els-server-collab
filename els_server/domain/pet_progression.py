"""Native pet stage/feed definitions plus explicitly agreed local growth policy."""
import functools,hashlib,json
from els_server.paths import PROJECT_ROOT
from els_server.game_data import CLIENT_SHA,client_data

@functools.lru_cache(maxsize=1)
def catalog():
    c=json.loads((PROJECT_ROOT/'analysis/pet-skills-20261015/progression-catalog.json').read_text(encoding='utf8'))
    if c['client_sha256']!=CLIENT_SHA or not c['all_item_dtos_passed']:raise ValueError('Pet progression build proof')
    for s in c['sources']:
        if hashlib.sha256((PROJECT_ROOT/s['path']).read_bytes()).hexdigest()!=s['sha256']:raise ValueError('Pet progression source changed')
    for i in c['definitions']:
        if hashlib.sha256(client_data().item(i['template'])['record']).hexdigest()!=i['record_sha256']:raise ValueError('Pet feed definition changed')
    return c

def template(unit):
    try:return catalog()['templates'][str(unit)]
    except KeyError:raise ValueError('Pet has no supported stage template') from None

def threshold(pet):return int(template(pet['unit'])['EVOLUTION_STEP_MAX'][str(pet['step']+1)])

def status(pet):return int(template(pet['unit'])['PET_STATUS'][str(pet['step']+1)])
