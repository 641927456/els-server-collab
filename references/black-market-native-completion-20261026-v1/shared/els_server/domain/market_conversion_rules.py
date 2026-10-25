"""Current KIM82/OptionConversion groups, with explicit finite local policies."""
from pathlib import Path
import functools,hashlib,json,secrets
from els_server.game_data import client_data,CLIENT_SHA
DATA_SHA='6f83afbe5acb350392a255e91853aa4b69b310940f9fbb673078a3e04bbe5f10'
@functools.lru_cache(maxsize=1)
def catalog():
 raw=(Path(__file__).resolve().parents[1]/'data/market_conversion.json').read_bytes()
 if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Market conversion fixed policy')
 c=json.loads(raw);d=client_data()
 if(c['schema']!=1 or c['client_sha256']!=CLIENT_SHA or c['catalog_sha256']!=d.manifest['catalog_sha256']or len(c['targets'])!=77 or set(c['coupons'])!={'119325','119329','136199','136201','136239','119343'}):raise ValueError('Market conversion finite source')
 for key,row in c['targets'].items():
  item=d.item(int(key))
  if item['metadata']!=1 or item['item_type']!=row['item_type']or item['equip_position']!=row['part']or hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']:raise ValueError('Market conversion target record')
 for key,row in c['coupons'].items():
  item=d.item(int(key))
  if item['item_type']!=7 or item['metadata']!=row['metadata']or hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']:raise ValueError('Market conversion coupon record')
 return c
def target(template):
 from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS
 row=catalog()['targets'].get(str(template))
 if row is None or(VERIFIED_TEMPLATES.get(template),TEMPLATE_BAG_GROUPS.get(template),TEMPLATE_MAX_STACKS.get(template))!=(1,1,1):raise ValueError('Registered original conversion target required')
 return row
def validate(template,values):
 t=target(template);r=catalog()['rules'][str(t['index'])]
 if not isinstance(values,(list,tuple))or len(values)!=t['slots']or any(type(v)is not int or str(v)not in r['families']for v in values):raise ValueError('Complete native conversion vector')
 if len({r['families'][str(v)]for v in values})!=len(values):raise ValueError('Native conversion distinct effects')
 return list(values)
def draw(template,randbelow=secrets.randbelow):
 t=target(template);r=catalog()['rules'][str(t['index'])];families=list(r['groups']);out=[]
 def pick(n):
  x=randbelow(n)
  if type(x)is not int or not 0<=x<n:raise ValueError('Market conversion random bounds')
  return x
 for _ in range(t['slots']):
  f=families.pop(pick(len(families)));ids=r['groups'][f];out.append(ids[pick(len(ids))])
 return validate(template,out)
def upgrade(template,values,slot,value):
 values=validate(template,values);r=catalog()['rules'][str(target(template)['index'])]
 if type(slot)is not int or not 0<=slot<len(values)or type(value)is not int or r['next'].get(str(values[slot]))!=value:raise ValueError('Only one exact native next-stage edge')
 values[slot]=value;return validate(template,values)
