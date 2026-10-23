"""Native existing weapon29 schema; uniform draws are labeled compatibility v1."""
import functools,hashlib,json
from pathlib import Path
from els_server.game_data import CLIENT_SHA,client_data
@functools.lru_cache(maxsize=1)
def catalog():
 p=Path(__file__).resolve().parents[1]/'data/option_conversion_existing.json';raw=p.read_bytes()
 if hashlib.sha256(raw).hexdigest()!='9a8cc2a4559e136788c6fc85ddd18b1fc5f1ed9747c5178d66140a998d95c8a7':raise ValueError('Existing conversion policy identity')
 c=json.loads(raw);d=client_data()
 if c['schema']!=1 or c['client_sha256']!=CLIENT_SHA or c['catalog_sha256']!=d.manifest['catalog_sha256']:raise ValueError('Existing conversion build identity')
 for key,row in c['targets'].items():
  item=d.item(int(key))
  if item['item_type']!=1 or item['metadata']!=1 or item['equip_position']!=2 or row['index']!=0 or row['slots']!=4 or hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']:raise ValueError('Existing conversion target source')
 return c

def target(template):
 from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
 row=catalog()['targets'].get(str(template))
 if row is None or VERIFIED_TEMPLATES.get(template)!=1 or TEMPLATE_BAG_GROUPS.get(template)!=1:raise ValueError('Registered native conversion weapon required')
 return row

def validate(template,values):
 row=target(template);families={v:k for k,ids in catalog()['families'].items() for v in ids}
 if not isinstance(values,(list,tuple))or len(values)!=row['slots']or any(type(v)is not int or v not in families for v in values):raise ValueError('Complete existing native weapon29 required')
 if len({families[v]for v in values})!=4:raise ValueError('Existing weapon29 families must be distinct')
 return list(values)

def draw(template,values,randbelow):
 validate(template,values);c=catalog();remaining=list(c['families']);result=[]
 def pick(n):
  value=randbelow(n)
  if type(value)is not int or not 0<=value<n:raise ValueError('Compatibility random range')
  return value
 for _ in range(4):
  family=remaining.pop(pick(len(remaining)));variants=c['families'][family];result.append(variants[pick(len(variants))])
 return validate(template,result)
