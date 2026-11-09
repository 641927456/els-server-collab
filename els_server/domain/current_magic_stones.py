"""Seven current stones, pinned native values and explicitly approved local weights."""
import functools,hashlib,json
from pathlib import Path
from els_server.game_data import CLIENT_SHA,client_data
from els_server.paths import PROJECT_ROOT
TEMPLATES=frozenset((132198,132202,132203,132204,132205,135793,710160))
@functools.lru_cache(maxsize=1)
def catalog():
 raw=(Path(__file__).resolve().parents[1]/'data/current_magic_stones.json').read_bytes()
 if hashlib.sha256(raw).hexdigest()!='e3ebba21207e997d1471c2a3069b24c623420bb3243cc0290b914ce575d745d2':raise ValueError('Current magic stone contract changed')
 d=json.loads(raw);c=client_data()
 if d['policy']!='seven-current-stones-description-compatibility-v1'or d['human_choice']!='call_7509d30e40394244a23eecd6524f89da'or d['client_sha256']!=CLIENT_SHA or d['catalog_sha256']!=c.manifest['catalog_sha256']or set(map(int,d['items']))!=TEMPLATES:raise ValueError('Current magic stone policy identity')
 for source in d['sources']:
  if hashlib.sha256((PROJECT_ROOT/source['path']).read_bytes()).hexdigest()!=source['sha256']:raise ValueError('Current native option source changed')
 for row in d['items'].values():
  item=c.item(row['template'])
  if item['item_type']!=7 or item['metadata']!=row['metadata']or hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']:raise ValueError('Current magic stone definition changed')
 for profile in d['profiles'].values():
  if sum(r['weight']for r in profile)!=10000 or len({r['option']for r in profile})!=len(profile)or any(type(r['weight'])is not int or r['weight']<=0 or str(r['option'])not in d['options']for r in profile):raise ValueError('Current magic stone distribution integrity')
 return d
