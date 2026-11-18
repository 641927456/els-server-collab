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
    # Existing verified PetData contains the current Odd Seed penalty. The
    # positive feeding-growth compatibility policy remains unchanged.
    calls=json.loads((PROJECT_ROOT/'analysis/pet-mount-20261015/resources/PetData.tables.json').read_bytes())['__symbolic_calls__']
    rates=[r['arguments'][1]for r in calls if r['function']=='g_pPetManager.SetDecreaseIntimacyRateForOddSeedOfElTree']
    special=[r['arguments'][1]for r in calls if r['function']=='g_pPetManager.AddSpecialFeedItemID']
    if rates!=[0.1001]or 185081 not in special:raise ValueError('Odd Seed current pet affinity source')
    c['odd_seed_rate']=rates[0]
    c['special_feed_ids']=frozenset(special)
    return c

def template(unit):
    try:return catalog()['templates'][str(unit)]
    except KeyError:raise ValueError('Pet has no supported stage template') from None

def threshold(pet):return int(template(pet['unit'])['EVOLUTION_STEP_MAX'][str(pet['step']+1)])

def status(pet):return int(template(pet['unit'])['PET_STATUS'][str(pet['step']+1)])
