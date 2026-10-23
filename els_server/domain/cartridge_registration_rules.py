"""Finite existing singleton Cartridge registration; explicit nonretail defaults.
No producer, ownership lookup, SQL, effects, binding or growth implementation.
"""
from pathlib import Path
import functools,hashlib,json
from els_server.game_data import client_data,CLIENT_SHA

DATA_SHA='79da62130f6cb09ec917f3c073d1e5dc228bc24023f1cb15459b4f5d45351582'
POLICY='cartridge-existing-singleton-register-account-v1'

@functools.lru_cache(maxsize=1)
def catalog():
 raw=(Path(__file__).resolve().parents[1]/'data/cartridge_registration.json').read_bytes()
 if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Cartridge registration data identity')
 p=json.loads(raw);data=client_data()
 if (p['schema_version']!=1 or p['policy_id']!=POLICY or p['official']is not False
     or p['client_sha256']!=CLIENT_SHA or p['catalog_sha256']!=data.manifest['catalog_sha256']
     or (p['initial_level'],p['initial_points'],p['duplicate_points'],p['max_points'])!=(1,0,200,50000)
     or p['overflow']!='reject_without_consume' or p['route']!='D4E_registration_only_unbound'
     or p['ownership_authorization_sha256']!='41349793189360285470fa6d0f478bcc0055a3fb9a19e9056d5d76fca220fe46'
     or p['numeric_decision_sha256']!='1e2a973535e77b370c0ff7849023c767ea20089f3a309ef6e7dfa846440f5b9f'):
  raise ValueError('Cartridge registration finite policy')
 rows=p['materials'];expected={119222+i:7+i for i in range(13)}|{119235+i:1+i for i in range(6)}
 if len(rows)!=19 or {r['template']:r['cartridge_id']for r in rows}!=expected:raise ValueError('Cartridge exact19 mapping')
 for r in rows:
  item=data.item(r['template'])
  if ((r['metadata'],r['group'],r['raw_max'],r['max_stack'])!=(0,4,0,1)
      or item['metadata']!=0 or item['item_type']!=7
      or hashlib.sha256(item['record']).hexdigest()!=r['record_sha256']):raise ValueError('Cartridge original material identity')
 return p

def materials():return tuple(dict(r)for r in catalog()['materials'])
def material(template):
 if type(template)is not int:raise ValueError('Cartridge material type')
 row=next((r for r in catalog()['materials']if r['template']==template),None)
 if row is None:raise ValueError('Unadmitted Cartridge material')
 return dict(row)

def source(item):
 row=material(item.get('template'))
 allowed={'uid','template','metadata','count','group','slot','expires_at','lock_until','sealed','seal_used'}
 if (set(item)-allowed or item.get('metadata')!=0 or item.get('count')!=1 or item.get('group')!=4
     or item.get('sealed',False)is not False or item.get('seal_used',0)!=0):raise ValueError('Cartridge singleton plain unsealed material')
 return row

def account_state(rows,points,revision):
 if type(rows)is not dict or len(rows)>19:raise ValueError('Cartridge account rows')
 if type(points)is not int or not 0<=points<=50000 or type(revision)is not int or not 0<=revision<2**63:raise ValueError('Cartridge account points/revision')
 for identity,pair in rows.items():
  if (type(identity)is not int or not 1<=identity<=19 or type(pair)not in(list,tuple)or len(pair)!=2
      or type(pair[0])is not int or pair[0]!=0 or type(pair[1])is not int or not 1<=pair[1]<=6):raise ValueError('Cartridge finite unbound logical state')
 return dict(rows={i:(0,v[1])for i,v in rows.items()},points=points,revision=revision)
