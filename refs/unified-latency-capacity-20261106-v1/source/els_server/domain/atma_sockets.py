"""Original Atma templates/option groups with official conditional weights."""
import functools,hashlib,json
from pathlib import Path
from els_server.game_data import CLIENT_SHA,client_data
from els_server.paths import PROJECT_ROOT

@functools.lru_cache(maxsize=1)
def catalog():
 raw=(Path(__file__).resolve().parents[1]/'data/atma_sockets.json').read_bytes()
 if hashlib.sha256(raw).hexdigest()!='bfa29bc3469da3194216a7e30bfa5cabb3c0ba73c8a9c8e94faf8b0ff3e60d34':raise ValueError('Atma catalog changed')
 c=json.loads(raw)
 if c['client_sha256']!=CLIENT_SHA or c['catalog_sha256']!=client_data().manifest['catalog_sha256']:raise ValueError('Atma client mismatch')
 for source in c['sources']:
  if hashlib.sha256((PROJECT_ROOT/source['path']).read_bytes()).hexdigest()!=source['sha256']:raise ValueError('Atma source changed')
 for r in c['items'].values():
  d=client_data().item(r['template'])
  if (d['item_type'],d['metadata'],r['group'])!=(7,r['metadata'],4) or hashlib.sha256(d['record']).hexdigest()!=r['record_sha256']:raise ValueError('Atma item mismatch')
 return c

def distribution(item,stone):
 d=client_data().item(item['template']);entry=catalog()['items'].get(str(stone))
 if entry is None or d['item_type'] not in (1,2):raise ValueError('Unsupported Atma target or material')
 kind='weapon' if d['item_type']==1 else 'armor'
 return catalog()['profiles'][str(entry['types'][kind])]

def valid_option(template,value):
 row=catalog()['options'].get(str(value))
 if row is None:return False
 item_type=client_data().item(template)['item_type']
 return item_type==1 and 771<=row['TYPE']<=786 or item_type==2 and 787<=row['TYPE']<=802
