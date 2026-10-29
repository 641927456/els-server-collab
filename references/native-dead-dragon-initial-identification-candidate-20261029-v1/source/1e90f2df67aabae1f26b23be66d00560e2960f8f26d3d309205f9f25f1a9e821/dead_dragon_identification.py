"""Finite136186 ordinary identification, exact3 native group slots.

Weights follow current exact death-dragon KR public effect groups matched to
pinned CN effect definitions, as this server's existing initial-ID contract.
This is not a claim that a private CN server RNG implementation was recovered.
"""
import functools,hashlib,json
from decimal import Decimal
from pathlib import Path
from els_server.game_data import CLIENT_SHA,client_data
from els_server.paths import PROJECT_ROOT

TEMPLATE=136186
PAYLOAD_SHA='4fdb83a74805dfa09506732dc52ae12e81df4c7016d9283c2c55a07787909aa5'

def supported(template):return type(template)is int and template==TEMPLATE

@functools.lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/dead_dragon_identification.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PAYLOAD_SHA:raise ValueError('Death-dragon identification payload identity')
    c=json.loads(raw)
    if(c['client_sha256']!=CLIENT_SHA or c['catalog_sha256']!=client_data().manifest['catalog_sha256']
            or c['template']!=TEMPLATE or c['native_groups']!=[1020,1015,1015]
            or c['official_groups']!=[6,5,5] or c['line_count']!=3
            or hashlib.sha256(client_data().item(TEMPLATE)['record']).hexdigest()!=c['record_sha256']):
        raise ValueError('Death-dragon exact native contract')
    definitions={}
    for source in c['native_option_sources']:
        value=(PROJECT_ROOT/source['path']).read_bytes()
        if hashlib.sha256(value).hexdigest()!=source['sha256']:raise ValueError('Death-dragon native option source changed')
        definitions.update({str(x['arguments'][1]['ID']):x['arguments'][1]
            for x in json.loads(value)['__symbolic_calls__']})
    for key,value in c['options'].items():
        if definitions.get(key)!=value:raise ValueError('Death-dragon native option definition changed')
    source=c['official_raw'].encode('utf8')
    if hashlib.sha256(source).hexdigest()!=c['official_raw_sha256']:raise ValueError('Death-dragon public probability identity')
    official=json.loads(source)
    if official['code']!=0 or len(official['data'])!=90:raise ValueError('Death-dragon official outcome coverage')
    for group in ('5','6'):
        pool=c['pools'][group];rows=[x for x in official['data']if x['groupno']==int(group)]
        if len(rows)!=45 or len(pool['outcomes'])!=45 or sum(x['weight']for x in pool['outcomes'])!=10000:
            raise ValueError('Death-dragon probability pool coverage')
        for original,outcome in zip(rows,pool['outcomes']):
            if(original['webitemid']!=4473 or original['option_str']!=outcome['official_label']
                    or Decimal(original['probability'])*100!=outcome['weight']
                    or str(outcome['option'])not in c['options'] or outcome['option']not in pool['allowed_ids']):
                raise ValueError('Death-dragon probability/native join')
    return c

def validate(template,values):
    if not supported(template):raise ValueError('Death-dragon identification target')
    c=catalog()
    if not isinstance(values,(list,tuple))or len(values)not in(0,3):raise ValueError('Death-dragon ordinary3-line vector')
    # Stored three-line vectors retain native equivalent aliases. Slot pools
    # constrain new draws only; loading never redraws an existing instance.
    allowed=set(c['historical_read_ids']).union(*(set(p['allowed_ids'])for p in c['pools'].values()))
    for value in values:
        if type(value)is not int or value not in allowed:
            raise ValueError('Death-dragon identification option/group')
    return list(values)

def initial_pending(item):
    if not supported(item['template']):return False
    if 'identified'in item:return False
    values=validate(TEMPLATE,item.get('option_groups',{}).get('1',[]))
    # Same bounded compatibility projection as the existing activity armors.
    # Explicit flags take priority in the existing ItemInfo writer. Worn legacy
    # items are read unchanged; no read-time SQL migration or random draw.
    return('identified'not in item and item['group']==1 and item['count']==1 and not values)

def draw(randbelow):
    c=catalog();values=[]
    # The exact weapon declares6/5/5 and the public source says one group/effect
    # does not change another's probability. Preserve the repeated slot; do not
    # deduplicate or reroll matching outcomes.
    for group in c['official_groups']:
        roll=randbelow(10000)
        if type(roll)is not int or not 0<=roll<10000:raise ValueError('Death-dragon random bound')
        for row in c['pools'][str(group)]['outcomes']:
            if roll<row['weight']:values.append(row['option']);break
            roll-=row['weight']
        else:raise ValueError('Death-dragon probability total')
    return validate(TEMPLATE,values)

def require_complete(item):
    if not supported(item['template']):return
    if item.get('identified')is True:return # Preserve explicit historical state.
    values=validate(TEMPLATE,item.get('option_groups',{}).get('1',[]))
    if item.get('identified')is False or not values:
        raise ValueError('Death-dragon weapon requires ordinary initial identification')
