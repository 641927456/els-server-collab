"""Fixed Sage and shining hunting: original values and verified weights only."""
import functools,hashlib,json
from pathlib import Path
from els_server.game_data import CLIENT_SHA,client_data
from els_server.paths import PROJECT_ROOT

@functools.lru_cache(maxsize=1)
def catalog():
 raw=(Path(__file__).resolve().parents[1]/'data/additional_magic_stones.json').read_bytes()
 if hashlib.sha256(raw).hexdigest()!='4d09c493ac6fde1bc7b5d7be774d09ab853b340f1d5152bca757e100e0e44907':raise ValueError('Additional magic stone catalog changed')
 c=json.loads(raw)
 if c['client_sha256']!=CLIENT_SHA or c['catalog_sha256']!=client_data().manifest['catalog_sha256']:raise ValueError('Additional stone client mismatch')
 for source in c['sources']:
  if hashlib.sha256((PROJECT_ROOT/source['path']).read_bytes()).hexdigest()!=source['sha256']:raise ValueError('Additional stone source changed')
 for r in c['items'].values():
  d=client_data().item(r['template'])
  if (d['item_type'],d['metadata'],r['group'])!=(7,r['metadata'],4) or hashlib.sha256(d['record']).hexdigest()!=r['record_sha256']:raise ValueError('Additional stone item mismatch')
 return c

def distribution(item,stone):
 d=client_data().item(item['template']);entry=catalog()['items'].get(str(stone))
 if entry is None or d['item_type'] not in (1,2):raise ValueError('Unsupported magic stone or target')
 kind='weapon' if d['item_type']==1 else 'armor'
 return catalog()['profiles'][entry['profiles'][kind]]

def valid_option(template,value):
 row=catalog()['options'].get(str(value))
 if row is None:return False
 item_type=client_data().item(template)['item_type']
 # Fixed Sage IDs already belong to the existing generic Sage whitelist.
 return item_type==1 and row['TYPE']==346 or item_type==2 and row['TYPE']==347
