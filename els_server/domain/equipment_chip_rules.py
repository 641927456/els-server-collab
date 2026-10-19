"""Finite native chip layout and explicitly compatible generation/tuning policy."""
import functools,hashlib,json,secrets
from els_server.paths import PROJECT_ROOT
from els_server.game_data import client_data,CLIENT_SHA

TEMPLATE=118638
DATA_SHA='55f9a7d7f8935dd622bd8d6b35bd193ba36d9370c1b83ed07d50c735df70ace6'

@functools.lru_cache(maxsize=1)
def catalog():
    raw=(PROJECT_ROOT/'els_server/data/equipment_chip.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Chip policy identity')
    c=json.loads(raw);data=client_data()
    if c['schema_version']!=1 or c['policy_id']!='equipment-chip-compatibility-v1' or c['client_sha256']!=CLIENT_SHA or c['catalog_sha256']!=data.manifest['catalog_sha256']:raise ValueError('Chip client identity')
    if c['material']['template']!=TEMPLATE or len(c['targets'])!=120 or len(c['options'])!=385:raise ValueError('Chip finite scope')
    for source in c['source_hashes']:
        if hashlib.sha256((PROJECT_ROOT/source['path']).read_bytes()).hexdigest()!=source['sha256']:raise ValueError('Chip original resource identity')
    for row in [c['material'],*c['targets'].values()]:
        if hashlib.sha256(data.item(row['template'])['record']).hexdigest()!=row['record_sha256']:raise ValueError('Chip item record identity')
    return c

def target(template):return catalog()['targets'].get(str(template))
def material(template):return template==TEMPLATE

def source_options(values):
    c=catalog()
    if not isinstance(values,(list,tuple)) or len(values)!=2 or any(type(v) is not int for v in values):raise ValueError('Chip requires exactly two base options')
    if str(values[0]) not in c['paths']['MERIT_SOCKET'] or str(values[1]) not in c['paths']['DEMERIT_SOCKET']:raise ValueError('Chip merit/demerit base order')
    return list(values)

def armor_options(template,values):
    c=catalog()
    if target(template) is None or not isinstance(values,(list,tuple)) or len(values)!=2 or any(type(v) is not int for v in values):raise ValueError('Chip armor options')
    total=0
    for family,value in zip(('MERIT_SOCKET','DEMERIT_SOCKET'),values):
        matches=[0 if value==int(base) else levels.index(value)+1 for base,levels in c['paths'][family].items() if value==int(base) or value in levels]
        if len(matches)!=1:raise ValueError('Unknown or ambiguous resolved chip option')
        total+=matches[0]
    if total>c['max_attempts']:raise ValueError('Installed chip exceeds ten total tuning attempts')
    return list(values)

@functools.lru_cache(maxsize=66)
def reachable_probabilities(attempts,successes):
    """Reachable states of this explicitly compatible policy, not retail RNG."""
    c=catalog()
    if not attempts:return frozenset((c['default_probability'],))
    result=set()
    if successes:
        result.update(max(c['minimum_probability'],p-c['probability_step']) for p in reachable_probabilities(attempts-1,successes-1))
    if successes<attempts:
        result.update(min(c['maximum_probability'],p+c['probability_step']) for p in reachable_probabilities(attempts-1,successes))
    return frozenset(result)

def state(template,values):
    c=catalog()
    if not material(template) or not isinstance(values,(list,tuple)) or len(values)!=4 or any(type(v) is not int for v in values):raise ValueError('Chip tuning bytes')
    attempts,successes,probability,reserved=values
    if not 0<=successes<=attempts<=c['max_attempts'] or reserved:raise ValueError('Chip tuning counter bounds')
    if (attempts==0 and probability not in (0,c['default_probability'])) or (attempts>0 and probability not in range(c['minimum_probability'],c['maximum_probability']+1,c['probability_step'])):raise ValueError('Chip tuning probability state')
    if (probability or c['default_probability']) not in reachable_probabilities(attempts,successes):raise ValueError('Unreachable compatible chip tuning state')
    return list(values)

def draw(size,randbelow):
    value=randbelow(size)
    if type(value) is not int or not 0<=value<size:raise ValueError('Chip random bound')
    return value

def generate(randbelow=secrets.randbelow):
    c=catalog();values=[]
    for family in ('MERIT_SOCKET','DEMERIT_SOCKET'):
        pool=sorted(map(int,c['paths'][family]));values.append(pool[draw(len(pool),randbelow)])
    return {'1':source_options(values)}

def resolved(item):
    c=catalog();options=source_options(item.get('option_groups',{}).get('1',[]));attempts,successes,_,_=state(item['template'],item.get('chip_tuning',[0,0,0,0]))
    values=[]
    for family,base,level in zip(('MERIT_SOCKET','DEMERIT_SOCKET'),options,(successes,attempts-successes)):
        values.append(base if not level else c['paths'][family][str(base)][level-1])
    return values

def advance(item,randbelow=secrets.randbelow):
    c=catalog();source_options(item.get('option_groups',{}).get('1',[]));old=state(item['template'],item.get('chip_tuning',[0,0,0,0]))
    attempts,successes,probability,_=old
    if attempts==c['max_attempts']:raise ValueError('Chip already has ten tuning attempts')
    success=draw(100,randbelow)<(probability or c['default_probability'])
    probability=max(c['minimum_probability'],min(c['maximum_probability'],(probability or c['default_probability'])+(-c['probability_step'] if success else c['probability_step'])))
    updated=state(item['template'],[attempts+1,successes+int(success),probability,0])
    # Original UI indexes this resource map with prior successes, not attempts.
    return updated,success,c['fees'][str(successes)]
