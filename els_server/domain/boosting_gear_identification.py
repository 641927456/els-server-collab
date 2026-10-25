"""Ordinary initial group1 effects for the exact60 activity Tenebros armors."""
import functools,hashlib,json
from decimal import Decimal
from pathlib import Path
from els_server.game_data import CLIENT_SHA,client_data

FIRST=721881
LAST=721940
POOL_SHA='4061462e5ca2119f45cef4f7d09ac899c1f97e308dd5fba7766b9fd18b74b8b7'

def supported(template):
    return type(template)is int and FIRST<=template<=LAST

@functools.lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/boosting_gear_identification.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=POOL_SHA:raise ValueError('Activity ordinary identification source changed')
    c=json.loads(raw)
    if(c['client_sha256']!=CLIENT_SHA or c['source_catalog_sha256']!=client_data().manifest['catalog_sha256']
            or c['line_count']!=3 or c['native_group']!=5160 or c['official_group']!=40
            or set(c['templates'])!={str(t)for t in range(FIRST,LAST+1)}):raise ValueError('Activity ordinary identification identity')
    for key,row in c['templates'].items():
        if(row['template']!=int(key)or row['metadata']!=1 or row['equip_position']not in(8,9,10,11)
                or row['native_groups']!=[5160]*3 or hashlib.sha256(client_data().item(int(key))['record']).hexdigest()!=row['record_sha256']):raise ValueError('Activity ordinary identification template')
    source=json.loads(c['official_raw'])
    if(source['code']!=0 or len(source['data'])!=40 or len(c['outcomes'])!=40 or len(c['options'])!=40
            or sum(r['weight']for r in c['outcomes'])!=10000):raise ValueError('Activity ordinary identification pool coverage')
    for original,row in zip(source['data'],c['outcomes']):
        if(original['webitemid']!=2166 or original['groupno']!=40 or original['option_str']!=row['official_label']
                or Decimal(original['probability'])*100!=row['weight']or type(row['option'])is not int
                or str(row['option'])not in c['options']):raise ValueError('Activity ordinary identification outcome')
    if(c['native_normalization']['field']!='m_fHyperModeTime' or c['native_normalization']['factor']!=1.5
            or c['options']['47821'].get('m_fAllSkillDamageIncreaseRate')!=0.005):raise ValueError('Activity ordinary native normalization')
    return c

def initial_pending(item):
    if not supported(item['template']):return False
    catalog()
    # View only: an already worn legacy item is retained; no SQL migration.
    # Explicit instance flags are handled first by the existing wire writer.
    return item['group']==1 and item['count']==1 and not item.get('option_groups',{}).get('1')

def validate(template,values):
    if not supported(template):raise ValueError('Activity ordinary identification target')
    c=catalog()
    if(not isinstance(values,(list,tuple))or len(values)not in(0,3)
            or any(type(v)is not int or str(v)not in c['options']for v in values)):
        raise ValueError('Activity ordinary three-line vector')
    return list(values)

def draw(randbelow):
    values=[]
    for unused in range(3):
        roll=randbelow(10000)
        if type(roll)is not int or not 0<=roll<10000:raise ValueError('Activity ordinary random bound')
        for row in catalog()['outcomes']:
            if roll<row['weight']:
                values.append(row['option']);break
            roll-=row['weight']
        else:raise ValueError('Activity ordinary pool incomplete')
    return validate(FIRST,values)

def require_complete(item):
    if supported(item['template']):
        if item.get('identified')is False or len(validate(item['template'],item.get('option_groups',{}).get('1',[])))!=3:
            raise ValueError('Activity armor requires ordinary initial identification')
