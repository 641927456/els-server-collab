"""Exact current regional drop material readers, native use and NPC recipes."""
import functools,hashlib,json,struct
from pathlib import Path

@functools.lru_cache(maxsize=1)
def catalog():
 from els_server.game_data import client_data,CLIENT_SHA
 p=Path(__file__).resolve().parents[1]/'data/regional_drop_materials.json';raw=p.read_bytes();m=json.loads(p.with_suffix('.manifest.json').read_bytes());c=json.loads(raw);d=client_data()
 if(hashlib.sha256(raw).hexdigest()!=m['payload_sha256']or c['client_sha256']!=m['client_sha256']or c['client_sha256']!=CLIENT_SHA or c['catalog_sha256']!=d.manifest['catalog_sha256']):raise ValueError('Regional material source identity')
 for r in c['items']:
  n=d.item(r['template'])
  if(hashlib.sha256(n['record']).hexdigest()!=r['record_sha256']or(n['name'],n['metadata'],n['item_type'],n['flags4'],n['flags8'])!=(r['name'],2,7,r['flags4'],56)or r['group']!=4 or r['max_stack']!=struct.unpack_from('<I',n['record'],16)[0]):raise ValueError('Regional material original reader')
 for r in c['recipes']:
  a=r['original_call']['arguments']
  if(r['original_call']['function']!='g_pItemManager.AddItemExchangeData'or a[1:7]!=[r['house'],1,r['source'],r['destination'],r['quantity'],100]or a[7]!={'m_iServerGroupID':-1,'m_iSourceQuantity':1}):raise ValueError('Regional material original exchange')
 return c

def definitions():return catalog()['items']
def source_only_templates():return frozenset(r['template']for r in definitions())
def boxes():return catalog()['boxes']
def raid_items(identity):return [tuple(r)for r in catalog()['raid_maps'].get(str(identity),[])]

def recipe(r,town):
 matches=[row for row in catalog()['recipes']if(row['house'],row['source'],row['town'])==(r.house,r.source,town)]
 if len(matches)!=1 or r.source_uid!=0 or r.source_quantity!=1 or r.destination!=0 or r.exchange_type!=1 or r.native_flag!=1 or r.native_index!=0 or not 1<=r.quantity<=1000:raise ValueError('Regional material exact NPC selection')
 return matches[0]
