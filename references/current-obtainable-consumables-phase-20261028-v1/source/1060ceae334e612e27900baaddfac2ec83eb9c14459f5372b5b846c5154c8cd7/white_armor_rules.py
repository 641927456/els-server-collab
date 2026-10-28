"""Current118655 character-native four armor pieces, per checked descriptions."""
from functools import lru_cache
from pathlib import Path
import hashlib,json
TEMPLATE=118655
POLICY='current-white-armor-description-mapping-20261028-v1'
DATA_SHA='5244cf7099e4a020bcffe9a68f9e21560b873320cb2b19f15dc42f8e0fe75c39'
@lru_cache(maxsize=1)
def catalog():
 raw=(Path(__file__).resolve().parents[1]/'data/white_armor_box.json').read_bytes()
 if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('White armor contract checksum')
 data=json.loads(raw)
 from els_server.game_data import client_data,CLIENT_SHA
 c=client_data()
 if data['client_sha256']!=CLIENT_SHA or data['catalog_sha256']!=c.manifest['catalog_sha256']or data['policy']!=POLICY or data['box']!=TEMPLATE or len(data['groups'])!=15:raise ValueError('White armor original identity')
 if hashlib.sha256(c.item(TEMPLATE)['record']).hexdigest()!=data['box_record_sha256']:raise ValueError('White armor box original template')
 seen=set()
 for group in data['groups']:
  unit=group['unit_type']
  if unit in seen or type(unit)is not int or not 1<=unit<=15 or len(group['outputs'])!=4:raise ValueError('White armor role groups')
  seen.add(unit)
  for index,output in enumerate(group['outputs']):
   item=c.item(output['template'])
   if hashlib.sha256(item['record']).hexdigest()!=output['record_sha256']or(item['metadata'],item['item_type'],item['equip_position'],item['record'][210])!=(1,2,8+index,unit)or output['quantity']!=1:raise ValueError('White armor current native output')
 return data
def outputs(unit):
 if type(unit)is not int:raise ValueError('White armor current character type')
 return next(g['outputs']for g in catalog()['groups']if g['unit_type']==unit)
def plan(unit):
 return[dict(template=r['template'],metadata=1,group=1,quantity=1)for r in outputs(unit)]
