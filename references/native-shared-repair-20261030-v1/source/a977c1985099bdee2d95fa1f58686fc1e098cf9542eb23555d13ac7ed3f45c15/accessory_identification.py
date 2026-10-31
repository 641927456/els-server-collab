"""One current accessory's original two-line initial identification."""
import functools,hashlib,json
from pathlib import Path
from decimal import Decimal
from els_server.game_data import client_data,CLIENT_SHA

TEMPLATE=30603

@functools.lru_cache(maxsize=1)
def catalog():
 raw=(Path(__file__).resolve().parents[1]/'data/accessory_identification.json').read_bytes()
 if hashlib.sha256(raw).hexdigest()!='d73724bdb404856457b3797b1a8ce3e07d3fb2f1517a03e2ffa90c17625a6448':raise ValueError('Accessory identification source changed')
 c=json.loads(raw);r=c['template']
 if(c['client_sha256']!=CLIENT_SHA or c['source_catalog_sha256']!=client_data().manifest['catalog_sha256']or r['template']!=TEMPLATE or r['current_native_groups']!=[5140,5140]or c['line_count']!=2 or c['official_group']!=35 or c['official_webitemid']!=2285):raise ValueError('Accessory identification identity')
 if hashlib.sha256(client_data().item(TEMPLATE)['record']).hexdigest()!=r['record_sha256']:raise ValueError('Accessory template changed')
 source=json.loads(c['official_raw']);assert source['code']==0
 if len(source['data'])!=41 or len(c['outcomes'])!=41 or len(c['options'])!=41 or sum(r['weight']for r in c['outcomes'])!=10000:raise ValueError('Accessory pool coverage')
 for original,outcome in zip(source['data'],c['outcomes']):
  if original['webitemid']!=2285 or original['groupno']!=35 or original['option_str']!=outcome['official_label']or Decimal(original['probability'])*100!=outcome['weight']or str(outcome['option'])not in c['options']:raise ValueError('Accessory pool join')
 return c

def supported(template):return template==TEMPLATE

def initial_pending(item):
 # View-only compatibility for an uninitialized bag item. Worn9 is unchanged,
 # and an explicit SQL flag or existing generated options always takes priority.
 if not supported(item['template']):return False
 catalog()
 return(item['group']==2 and item['count']==1 and not item.get('option_groups',{}).get('1'))

def validate(template,values):
 if not supported(template):raise ValueError('Accessory identification template')
 c=catalog()
 if not isinstance(values,(list,tuple))or len(values)not in(0,2)or any(type(v)is not int or str(v)not in c['options']for v in values):raise ValueError('Accessory identification vector')
 return list(values)

def draw(randbelow):
 from els_server.domain.identification_ui import draw_slots
 result=draw_slots(lambda:catalog()['outcomes'],catalog()['line_count'],randbelow,10000,
                   range_error='Accessory random bound',
                   incomplete_error='Accessory pool incomplete')
 return validate(TEMPLATE,result)
