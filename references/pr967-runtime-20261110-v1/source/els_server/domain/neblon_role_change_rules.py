"""Finite current Neblon role-change families and approved existing-coupon policy."""
from pathlib import Path
import functools,hashlib,json
from els_server.game_data import client_data,CLIENT_SHA
DATA_SHA='fe3c7b4f3b9988a95772616e68881563d3e4d0bb32236ef39d8d5640574e1a3d'

@functools.lru_cache(maxsize=1)
def catalog():
 raw=(Path(__file__).resolve().parents[1]/'data/neblon_role_change.json').read_bytes()
 if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Neblon role policy identity')
 p=json.loads(raw);d=client_data()
 if(p['schema']!=1 or p['policy_id']!='F-native-neblon-suit-role-change-v1'
    or p['client_sha256']!=CLIENT_SHA or p['catalog_sha256']!=d.manifest['catalog_sha256']
    or(p['town'],p['scene'],p['house'],p['npc'],p['button'])!=(1012,1214,40327,10501,14)
    or(p['request_kind'],p['ack_kind'],p['coupon_quantity'],p['additional_ED'])!=(0xd56,0xd57,1,0)
    or not p['fee_and_priority_explicit_server_rules']or len(p['families'])!=4
    or len(p['records'])!=60 or len(p['coupons'])!=8 or p['new_item_sources']!=0):
  raise ValueError('Finite Neblon role-change policy')
 seen=set();materials=set()
 for f in p['families']:
  if len(f['templates'])!=15 or len(set(f['templates']))!=15 or len(f['coupons'])!=2:raise ValueError('Native Neblon family sizes')
  for t in f['templates']:
   r=p['records'][str(t)];v=d.item(t)
   if t in seen or r['part']!=f['part']or(v['metadata'],v['item_type'],v['equip_position'])!=(1,2,f['part']):raise ValueError('Original Neblon family identity')
   if hashlib.sha256(v['record']).hexdigest()!=r['record_sha256']:raise ValueError('Original Neblon armor record')
   seen.add(t)
  for t in f['coupons']:
   r=p['coupons'][str(t)];v=d.item(t)
   if t in materials or(v['metadata'],v['item_type'],r['metadata'],r['group'],r['max_stack'])!=(0,7,0,4,1):raise ValueError('Original Neblon singleton coupon')
   if hashlib.sha256(v['record']).hexdigest()!=r['record_sha256']or int.from_bytes(v['record'][16:20],'little')!=r['raw_max']:raise ValueError('Original Neblon coupon record')
   materials.add(t)
 if seen!={int(k)for k in p['records']}or materials!={int(k)for k in p['coupons']}:raise ValueError('Neblon finite set coverage')
 return p

def definitions():return tuple(dict(r)for r in catalog()['coupons'].values())

def owned_only_templates():return frozenset(r['template']for r in catalog()['coupons'].values()if r['new_owned_reader_only'])

def family(source,target):
 if type(source)is not int or type(target)is not int or source==target:raise ValueError('Neblon distinct native templates')
 f=next((f for f in catalog()['families']if source in f['templates']),None)
 if f is None or target not in f['templates']:raise ValueError('Neblon same-part native role family')
 return f
